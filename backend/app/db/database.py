import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

from app.core.config import settings


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_uuid() -> str:
    return str(uuid.uuid4())


def _resolve_sqlite_path(db_url: Optional[str] = None) -> str:
    url = db_url or settings.DATABASE_URL
    if url.startswith("sqlite:///"):
        path = url.replace("sqlite:///", "", 1)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        return path
    raise RuntimeError("Unsupported DATABASE_URL: use sqlite:///path or postgresql://...")


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

-- 1. Users
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 2. Organizations
CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    settings_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 3. Organization Memberships
CREATE TABLE IF NOT EXISTS organization_memberships (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('ADMIN', 'MANAGER', 'MEMBER')),
    created_at TEXT NOT NULL,
    UNIQUE(organization_id, user_id)
);

-- 4. Meetings
CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    created_by TEXT NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    summary TEXT,
    meeting_date TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'transcript_text',
    audio_file_path TEXT,
    status TEXT NOT NULL DEFAULT 'UPLOADED' CHECK(status IN ('UPLOADED', 'PROCESSING', 'PROCESSED', 'FAILED')),
    topics_json TEXT NOT NULL DEFAULT '[]',
    pipeline_log_json TEXT NOT NULL DEFAULT '[]',
    is_deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 5. Meeting Participants
CREATE TABLE IF NOT EXISTS meeting_participants (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    display_name TEXT NOT NULL,
    role_in_meeting TEXT DEFAULT 'participant',
    created_at TEXT NOT NULL
);

-- 6. Transcripts
CREATE TABLE IF NOT EXISTS transcripts (
    id TEXT PRIMARY KEY,
    meeting_id TEXT UNIQUE NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    raw_text TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'whisper_compatible',
    language TEXT NOT NULL DEFAULT 'en',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 7. Speakers
CREATE TABLE IF NOT EXISTS speakers (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    speaker_key TEXT NOT NULL,
    speaker_label TEXT NOT NULL,
    mapped_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    is_unknown INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 8. Transcript Segments
CREATE TABLE IF NOT EXISTS transcript_segments (
    id TEXT PRIMARY KEY,
    transcript_id TEXT NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    speaker_id TEXT REFERENCES speakers(id) ON DELETE SET NULL,
    speaker_label TEXT NOT NULL,
    text TEXT NOT NULL,
    start_time REAL NOT NULL DEFAULT 0.0,
    end_time REAL NOT NULL DEFAULT 0.0,
    confidence REAL,
    segment_index INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 9. Decisions
CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    source_segment_id TEXT REFERENCES transcript_segments(id) ON DELETE SET NULL,
    subject TEXT NOT NULL,
    statement TEXT NOT NULL,
    decision_type TEXT NOT NULL CHECK(decision_type IN ('CONFIRMED', 'PROPOSED', 'REJECTED', 'SUPERSEDED', 'UNRESOLVED')),
    status TEXT NOT NULL DEFAULT 'PENDING_REVIEW' CHECK(status IN ('PENDING_REVIEW', 'CONFIRMED', 'SUPERSEDED', 'REJECTED')),
    key_value TEXT,
    evidence_quote TEXT,
    participants_json TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0.85,
    needs_review INTEGER NOT NULL DEFAULT 0,
    embedding_json TEXT NOT NULL DEFAULT '[]',
    current_version INTEGER NOT NULL DEFAULT 1,
    confirmed_by TEXT REFERENCES users(id) ON DELETE SET NULL,
    confirmed_at TEXT,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 10. Decision Versions
CREATE TABLE IF NOT EXISTS decision_versions (
    id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    statement TEXT NOT NULL,
    key_value TEXT,
    status TEXT NOT NULL,
    source_meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    evidence_quote TEXT,
    changed_by TEXT REFERENCES users(id) ON DELETE SET NULL,
    change_reason TEXT,
    created_at TEXT NOT NULL
);

-- 11. Decision Relationships
CREATE TABLE IF NOT EXISTS decision_relationships (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    source_decision_id TEXT NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
    target_decision_id TEXT NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL CHECK(relationship_type IN ('SUPERSEDES', 'CONFLICTS_WITH', 'EXTENDS', 'RELATED_TO')),
    similarity_score REAL,
    created_at TEXT NOT NULL
);

-- 12. Decision Conflicts
CREATE TABLE IF NOT EXISTS decision_conflicts (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    existing_decision_id TEXT NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
    new_decision_id TEXT NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
    existing_meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    new_meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    conflict_type TEXT NOT NULL CHECK(conflict_type IN ('DEADLINE_CHANGE', 'CONTRADICTION', 'SCOPE_CHANGE', 'SUPERSEDED_PROPOSAL')),
    severity TEXT NOT NULL DEFAULT 'HIGH' CHECK(severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    explanation TEXT NOT NULL,
    suggested_resolution TEXT NOT NULL,
    existing_evidence TEXT,
    new_evidence TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN', 'RESOLVED_KEEP_EXISTING', 'RESOLVED_ADOPT_NEW', 'DISMISSED')),
    resolved_by TEXT REFERENCES users(id) ON DELETE SET NULL,
    resolved_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 13. Action Items
CREATE TABLE IF NOT EXISTS action_items (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    meeting_id TEXT REFERENCES meetings(id) ON DELETE SET NULL,
    source_segment_id TEXT REFERENCES transcript_segments(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT,
    assigned_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    assigned_name TEXT,
    deadline TEXT,
    priority TEXT NOT NULL DEFAULT 'MEDIUM' CHECK(priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')),
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN', 'IN_PROGRESS', 'COMPLETED', 'BLOCKED', 'CANCELLED')),
    dependencies_json TEXT NOT NULL DEFAULT '[]',
    evidence_quote TEXT,
    confidence REAL NOT NULL DEFAULT 0.85,
    review_status TEXT NOT NULL DEFAULT 'NEEDS_REVIEW' CHECK(review_status IN ('NEEDS_REVIEW', 'APPROVED', 'REJECTED')),
    external_provider TEXT,
    external_task_id TEXT,
    sync_status TEXT NOT NULL DEFAULT 'NOT_SYNCED',
    is_deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 14. Approvals (Central Human Approval Gate)
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL CHECK(action_type IN (
        'EXTERNAL_TASK_CREATE', 'EXTERNAL_TASK_UPDATE', 'DEADLINE_REMINDER',
        'WEEKLY_DIGEST', 'EMAIL_DISPATCH', 'CALENDAR_UPDATE',
        'DECISION_PUBLISH', 'NOTIFICATION_DISPATCH'
    )),
    target_provider TEXT NOT NULL,
    proposed_content_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    source_meeting_id TEXT REFERENCES meetings(id) ON DELETE SET NULL,
    source_entity_id TEXT,
    supporting_evidence TEXT,
    requested_by TEXT NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN (
        'PENDING', 'APPROVED', 'REJECTED', 'EXECUTING', 'EXECUTED', 'FAILED', 'CANCELLED'
    )),
    reviewer_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TEXT,
    review_comment TEXT,
    recurring_policy_id TEXT,
    execution_error TEXT,
    executed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 15. Integration Connections
CREATE TABLE IF NOT EXISTS integration_connections (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK(provider IN ('linear', 'trello', 'google_calendar', 'email', 'slack')),
    workspace_name TEXT,
    project_id TEXT,
    config_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'CONNECTED' CHECK(status IN ('CONNECTED', 'DISCONNECTED', 'ERROR')),
    connected_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(organization_id, provider)
);

-- 16. External Execution Records
CREATE TABLE IF NOT EXISTS external_execution_records (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    approval_id TEXT NOT NULL REFERENCES approvals(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    external_reference_id TEXT,
    request_payload_json TEXT NOT NULL,
    response_payload_json TEXT,
    status TEXT NOT NULL CHECK(status IN ('SUCCESS', 'FAILED')),
    attempt_count INTEGER NOT NULL DEFAULT 1,
    executed_by TEXT REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);

-- 17. Notifications
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    notification_type TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    related_entity_id TEXT,
    created_at TEXT NOT NULL
);

-- 18. Reminders
CREATE TABLE IF NOT EXISTS reminders (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    action_item_id TEXT NOT NULL REFERENCES action_items(id) ON DELETE CASCADE,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    scheduled_for TEXT NOT NULL,
    reminder_type TEXT NOT NULL DEFAULT 'UPCOMING' CHECK(reminder_type IN ('UPCOMING', 'OVERDUE', 'ESCALATION')),
    timezone TEXT NOT NULL DEFAULT 'UTC',
    status TEXT NOT NULL DEFAULT 'PENDING_APPROVAL' CHECK(status IN ('PENDING_APPROVAL', 'APPROVED', 'SENT', 'CANCELLED')),
    approval_id TEXT REFERENCES approvals(id) ON DELETE SET NULL,
    dedup_key TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 19. Weekly Digests
CREATE TABLE IF NOT EXISTS weekly_digests (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    delivery_day TEXT NOT NULL DEFAULT 'Monday',
    delivery_time TEXT NOT NULL DEFAULT '09:00',
    timezone TEXT NOT NULL DEFAULT 'UTC',
    digest_format TEXT NOT NULL DEFAULT 'markdown',
    content_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING_APPROVAL' CHECK(status IN ('PENDING_APPROVAL', 'APPROVED', 'SENT', 'REJECTED')),
    approval_id TEXT REFERENCES approvals(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 20. Audit Logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    actor_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_meetings_org ON meetings(organization_id);
CREATE INDEX IF NOT EXISTS idx_decisions_org ON decisions(organization_id);
CREATE INDEX IF NOT EXISTS idx_conflicts_org ON decision_conflicts(organization_id);
CREATE INDEX IF NOT EXISTS idx_tasks_org ON action_items(organization_id);
CREATE INDEX IF NOT EXISTS idx_approvals_org_status ON approvals(organization_id, status);
CREATE INDEX IF NOT EXISTS idx_reminders_org ON reminders(organization_id);
CREATE INDEX IF NOT EXISTS idx_digests_org_user ON weekly_digests(organization_id, user_id);
CREATE INDEX IF NOT EXISTS idx_audit_org ON audit_logs(organization_id);
"""


class _PostgresRow(dict):
    pass


class _PostgresResult:
    def __init__(self, result):
        self._result = result

    @property
    def rowcount(self) -> int:
        return self._result.rowcount

    @staticmethod
    def _normalize_row(row) -> _PostgresRow:
        mapping = row._mapping
        normalized = {}
        for key, value in mapping.items():
            if hasattr(value, "isoformat"):
                normalized[key] = value.isoformat()
            elif hasattr(value, "hex"):
                normalized[key] = str(value)
            else:
                normalized[key] = value
        return _PostgresRow(normalized)

    def fetchone(self) -> Optional[_PostgresRow]:
        row = self._result.fetchone()
        return None if row is None else self._normalize_row(row)

    def fetchall(self) -> List[_PostgresRow]:
        return [self._normalize_row(row) for row in self._result.fetchall()]


class _PostgresConnection:
    def __init__(self, connection):
        self._connection = connection

    def execute(self, sql: str, params: Optional[Any] = None):
        query = sql
        bindings = {}
        if params is not None:
            if isinstance(params, (tuple, list)):
                parts = []
                for index, value in enumerate(params):
                    parts.append(f":p{index}")
                    bindings[f"p{index}"] = value
                for index, placeholder in enumerate(parts):
                    query = query.replace("?", placeholder, 1)
            else:
                bindings = dict(params)
        result = self._connection.execute(text(query), bindings)
        return _PostgresResult(result)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


class Database:
    def __init__(self, db_url: Optional[str] = None):
        self.url = db_url or settings.DATABASE_URL
        self.db_path: Optional[str] = None
        self.engine: Optional[Engine] = None
        if self.url.startswith("sqlite"):
            self.db_path = _resolve_sqlite_path(self.url)
        elif self.url.startswith(("postgresql://", "postgresql+psycopg2://")):
            parsed = urlparse(self.url)
            if parsed.hostname and parsed.port:
                pass
            sqlalchemy_url = (
                self.url if "+psycopg2" in self.url
                else self.url.replace("postgresql://", "postgresql+psycopg2://", 1)
            )
            self.engine = create_engine(
                sqlalchemy_url,
                poolclass=QueuePool,
                pool_pre_ping=True,
                pool_recycle=1800,
            )
        else:
            raise RuntimeError(f"Unsupported DATABASE_URL scheme: {self.url}")
        self.init_db()

    def connect(self):
        if self.engine is not None:
            return _PostgresConnection(self.engine.connect())
        conn = sqlite3.connect(self.db_path or "", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_db(self) -> None:
        if self.engine is not None:
            return
        conn = self.connect()
        try:
            conn.executescript(SCHEMA_SQL)
            conn.commit()
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Generator[Any, None, None]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


db = Database()


def get_db() -> Generator[Any, None, None]:
    conn = db.connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def record_audit_log(
    conn: sqlite3.Connection,
    organization_id: str,
    actor_user_id: Optional[str],
    event_type: str,
    entity_type: str,
    entity_id: str,
    details: Optional[Dict[str, Any]] = None,
) -> str:
    log_id = new_uuid()
    conn.execute(
        """
        INSERT INTO audit_logs (id, organization_id, actor_user_id, event_type, entity_type, entity_id, details_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            log_id,
            organization_id,
            actor_user_id,
            event_type,
            entity_type,
            entity_id,
            json.dumps(details or {}, default=str),
            utc_now(),
        ),
    )
    return log_id
