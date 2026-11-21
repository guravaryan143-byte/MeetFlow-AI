import json
import sqlite3
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.approvals.execution_service import AUTHORIZED_APPROVER_ROLES
from app.db.database import get_db, new_uuid, record_audit_log, utc_now
from app.schemas.schemas import DecisionConfirmRequest

router = APIRouter(prefix="/api/decisions", tags=["Decisions"])


@router.get("")
def list_decisions(
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = conn.execute(
        """
        SELECT d.*, m.title AS meeting_title, m.meeting_date AS meeting_date
        FROM decisions d
        JOIN meetings m ON d.meeting_id = m.id
        WHERE d.organization_id = ? AND d.is_deleted = 0
        ORDER BY d.created_at DESC
        """,
        (current_user["organization_id"],),
    ).fetchall()
    decisions = []
    for r in rows:
        item = dict(r)
        item["participants"] = json.loads(item.pop("participants_json") or "[]")
        item.pop("embedding_json", None)
        decisions.append(item)
    return {"decisions": decisions}


@router.get("/conflicts")
def list_conflicts(
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = conn.execute(
        """
        SELECT c.*,
               m1.title AS existing_meeting_title,
               m2.title AS new_meeting_title,
               d1.subject AS existing_subject,
               d1.statement AS existing_statement,
               d1.key_value AS existing_value,
               d2.statement AS new_statement,
               d2.key_value AS new_value
        FROM decision_conflicts c
        JOIN meetings m1 ON c.existing_meeting_id = m1.id
        JOIN meetings m2 ON c.new_meeting_id = m2.id
        JOIN decisions d1 ON c.existing_decision_id = d1.id
        JOIN decisions d2 ON c.new_decision_id = d2.id
        WHERE c.organization_id = ?
        ORDER BY c.created_at DESC
        """,
        (current_user["organization_id"],),
    ).fetchall()
    return {"conflicts": [dict(r) for r in rows]}


@router.get("/{decision_id}")
def get_decision(
    decision_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute(
        """
        SELECT d.*, m.title AS meeting_title, m.meeting_date AS meeting_date
        FROM decisions d
        JOIN meetings m ON d.meeting_id = m.id
        WHERE d.id = ? AND d.organization_id = ? AND d.is_deleted = 0
        """,
        (decision_id, current_user["organization_id"]),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Decision not found.")

    item = dict(row)
    item["participants"] = json.loads(item.pop("participants_json") or "[]")
    item.pop("embedding_json", None)

    versions = [
        dict(v)
        for v in conn.execute(
            """
            SELECT dv.*, m.title AS source_meeting_title
            FROM decision_versions dv
            JOIN meetings m ON dv.source_meeting_id = m.id
            WHERE dv.decision_id = ? AND dv.organization_id = ?
            ORDER BY dv.version_number ASC
            """,
            (decision_id, current_user["organization_id"]),
        ).fetchall()
    ]
    relationships = [
        dict(rel)
        for rel in conn.execute(
            """
            SELECT * FROM decision_relationships
            WHERE organization_id = ? AND (source_decision_id = ? OR target_decision_id = ?)
            """,
            (current_user["organization_id"], decision_id, decision_id),
        ).fetchall()
    ]
    conflicts = [
        dict(c)
        for c in conn.execute(
            """
            SELECT * FROM decision_conflicts
            WHERE organization_id = ? AND (existing_decision_id = ? OR new_decision_id = ?)
            """,
            (current_user["organization_id"], decision_id, decision_id),
        ).fetchall()
    ]
    item["versions"] = versions
    item["relationships"] = relationships
    item["conflicts"] = conflicts
    return item


@router.post("/{decision_id}/confirm")
def confirm_decision(
    decision_id: str,
    payload: DecisionConfirmRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    if current_user["role"] not in AUTHORIZED_APPROVER_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Only ADMIN or MANAGER roles can confirm or resolve decisions.",
        )

    dec = conn.execute(
        "SELECT * FROM decisions WHERE id = ? AND organization_id = ? AND is_deleted = 0",
        (decision_id, current_user["organization_id"]),
    ).fetchone()
    if not dec:
        raise HTTPException(status_code=404, detail="Decision not found.")

    now = utc_now()
    new_version = dec["current_version"] + 1

    if payload.resolution_action == "REJECT":
        conn.execute(
            """
            UPDATE decisions
            SET status = 'REJECTED', needs_review = 0, confirmed_by = ?, confirmed_at = ?,
                current_version = ?, updated_at = ?
            WHERE id = ?
            """,
            (current_user["user_id"], now, new_version, now, decision_id),
        )
        new_status = "REJECTED"
    else:
        conn.execute(
            """
            UPDATE decisions
            SET status = 'CONFIRMED', decision_type = 'CONFIRMED', needs_review = 0,
                confirmed_by = ?, confirmed_at = ?, current_version = ?, updated_at = ?
            WHERE id = ?
            """,
            (current_user["user_id"], now, new_version, now, decision_id),
        )
        new_status = "CONFIRMED"

    # Append immutable Decision Version (never overwrite history)
    conn.execute(
        """
        INSERT INTO decision_versions (
            id, decision_id, organization_id, version_number, statement, key_value,
            status, source_meeting_id, evidence_quote, changed_by, change_reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_uuid(),
            decision_id,
            current_user["organization_id"],
            new_version,
            dec["statement"],
            dec["key_value"],
            new_status,
            dec["meeting_id"],
            dec["evidence_quote"],
            current_user["user_id"],
            payload.change_reason or f"Authorized resolution: {payload.resolution_action}",
            now,
        ),
    )

    # If resolving a conflict, preserve historical decision as SUPERSEDED rather than deleting/overwriting
    if payload.conflict_id:
        conflict = conn.execute(
            "SELECT * FROM decision_conflicts WHERE id = ? AND organization_id = ?",
            (payload.conflict_id, current_user["organization_id"]),
        ).fetchone()
        if conflict:
            if payload.resolution_action in {"ADOPT_NEW", "CONFIRM"}:
                old_id = conflict["existing_decision_id"]
                old_dec = conn.execute("SELECT * FROM decisions WHERE id = ?", (old_id,)).fetchone()
                if old_dec and old_id != decision_id:
                    old_ver = old_dec["current_version"] + 1
                    conn.execute(
                        "UPDATE decisions SET status = 'SUPERSEDED', current_version = ?, updated_at = ? WHERE id = ?",
                        (old_ver, now, old_id),
                    )
                    conn.execute(
                        """
                        INSERT INTO decision_versions (
                            id, decision_id, organization_id, version_number, statement, key_value,
                            status, source_meeting_id, evidence_quote, changed_by, change_reason, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, 'SUPERSEDED', ?, ?, ?, ?, ?)
                        """,
                        (
                            new_uuid(),
                            old_id,
                            current_user["organization_id"],
                            old_ver,
                            old_dec["statement"],
                            old_dec["key_value"],
                            old_dec["meeting_id"],
                            old_dec["evidence_quote"],
                            current_user["user_id"],
                            f"Superseded by confirmed decision {decision_id}",
                            now,
                        ),
                    )
                    conn.execute(
                        """
                        INSERT INTO decision_relationships (
                            id, organization_id, source_decision_id, target_decision_id,
                            relationship_type, created_at
                        ) VALUES (?, ?, ?, ?, 'SUPERSEDES', ?)
                        """,
                        (new_uuid(), current_user["organization_id"], decision_id, old_id, now),
                    )
                conn.execute(
                    """
                    UPDATE decision_conflicts
                    SET status = 'RESOLVED_ADOPT_NEW', resolved_by = ?, resolved_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (current_user["user_id"], now, now, payload.conflict_id),
                )
            elif payload.resolution_action == "KEEP_EXISTING":
                conn.execute(
                    """
                    UPDATE decision_conflicts
                    SET status = 'RESOLVED_KEEP_EXISTING', resolved_by = ?, resolved_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (current_user["user_id"], now, now, payload.conflict_id),
                )

    record_audit_log(
        conn,
        current_user["organization_id"],
        current_user["user_id"],
        "DECISION_CONFIRMED",
        "decision",
        decision_id,
        {
            "resolution_action": payload.resolution_action,
            "conflict_id": payload.conflict_id,
            "new_version": new_version,
        },
    )

    return get_decision(decision_id, current_user, conn)
