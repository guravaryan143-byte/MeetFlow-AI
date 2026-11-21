import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.agents.orchestrator import MeetingPipelineOrchestrator
from app.agents.providers import AIProviderError
from app.agents.transcription import validate_upload_file
from app.api.deps import get_current_user
from app.core.config import settings
from app.db.database import get_db, new_uuid, record_audit_log, utc_now
from app.schemas.schemas import MeetingCreateRequest

router = APIRouter(prefix="/api/meetings", tags=["Meetings"])
orchestrator = MeetingPipelineOrchestrator()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_meeting(
    payload: MeetingCreateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    now = utc_now()
    meeting_id = new_uuid()
    meeting_date = payload.meeting_date or now[:10]

    conn.execute(
        """
        INSERT INTO meetings (
            id, organization_id, created_by, title, meeting_date,
            source_type, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'transcript_text', 'UPLOADED', ?, ?)
        """,
        (
            meeting_id,
            current_user["organization_id"],
            current_user["user_id"],
            payload.title,
            meeting_date,
            now,
            now,
        ),
    )

    for name in payload.participants:
        conn.execute(
            """
            INSERT INTO meeting_participants (id, meeting_id, display_name, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (new_uuid(), meeting_id, name, now),
        )

    if payload.transcript_text:
        conn.execute(
            """
            INSERT INTO transcripts (id, meeting_id, organization_id, raw_text, provider, language, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'direct_input', 'en', ?, ?)
            """,
            (
                new_uuid(),
                meeting_id,
                current_user["organization_id"],
                payload.transcript_text,
                now,
                now,
            ),
        )

    record_audit_log(
        conn,
        current_user["organization_id"],
        current_user["user_id"],
        "MEETING_CREATED",
        "meeting",
        meeting_id,
        {"title": payload.title},
    )

    return {
        "id": meeting_id,
        "title": payload.title,
        "meeting_date": meeting_date,
        "status": "UPLOADED",
        "created_at": now,
    }


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_meeting_file(
    title: str = Form(...),
    meeting_date: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    content = await file.read(settings.MAX_UPLOAD_SIZE_BYTES + 1)
    if len(content) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB.",
        )
    try:
        kind, ext = validate_upload_file(file.filename or "", len(content))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    now = utc_now()
    meeting_id = new_uuid()
    safe_name = f"{meeting_id}{ext}"
    org_upload_dir = settings.UPLOAD_DIR / current_user["organization_id"]
    org_upload_dir.mkdir(parents=True, exist_ok=True)
    saved_path = org_upload_dir / safe_name
    saved_path.write_bytes(content)

    conn.execute(
        """
        INSERT INTO meetings (
            id, organization_id, created_by, title, meeting_date,
            source_type, audio_file_path, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'UPLOADED', ?, ?)
        """,
        (
            meeting_id,
            current_user["organization_id"],
            current_user["user_id"],
            title,
            meeting_date or now[:10],
            f"{kind}_upload",
            str(saved_path) if kind == "audio" else None,
            now,
            now,
        ),
    )

    if kind == "transcript":
        raw_text = content.decode("utf-8", errors="replace")
        conn.execute(
            """
            INSERT INTO transcripts (id, meeting_id, organization_id, raw_text, provider, language, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'file_upload', 'en', ?, ?)
            """,
            (new_uuid(), meeting_id, current_user["organization_id"], raw_text, now, now),
        )

    record_audit_log(
        conn,
        current_user["organization_id"],
        current_user["user_id"],
        "MEETING_FILE_UPLOADED",
        "meeting",
        meeting_id,
        {"filename": file.filename, "kind": kind, "size_bytes": len(content)},
    )

    return {
        "id": meeting_id,
        "title": title,
        "source_type": f"{kind}_upload",
        "status": "UPLOADED",
        "filename": file.filename,
        "size_bytes": len(content),
    }


@router.get("")
def list_meetings(
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = conn.execute(
        """
        SELECT * FROM meetings
        WHERE organization_id = ? AND is_deleted = 0
        ORDER BY created_at DESC
        """,
        (current_user["organization_id"],),
    ).fetchall()
    result = []
    for r in rows:
        item = dict(r)
        item["topics"] = json.loads(item.pop("topics_json") or "[]")
        item["pipeline_log"] = json.loads(item.pop("pipeline_log_json") or "[]")
        result.append(item)
    return {"meetings": result}


@router.get("/{meeting_id}")
def get_meeting(
    meeting_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute(
        "SELECT * FROM meetings WHERE id = ? AND organization_id = ? AND is_deleted = 0",
        (meeting_id, current_user["organization_id"]),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    meeting = dict(row)
    meeting["topics"] = json.loads(meeting.pop("topics_json") or "[]")
    meeting["pipeline_log"] = json.loads(meeting.pop("pipeline_log_json") or "[]")

    decisions = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM decisions WHERE meeting_id = ? AND organization_id = ? AND is_deleted = 0",
            (meeting_id, current_user["organization_id"]),
        ).fetchall()
    ]
    tasks = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM action_items WHERE meeting_id = ? AND organization_id = ? AND is_deleted = 0",
            (meeting_id, current_user["organization_id"]),
        ).fetchall()
    ]
    conflicts = [
        dict(r)
        for r in conn.execute(
            """
            SELECT * FROM decision_conflicts
            WHERE organization_id = ? AND (existing_meeting_id = ? OR new_meeting_id = ?)
            """,
            (current_user["organization_id"], meeting_id, meeting_id),
        ).fetchall()
    ]
    meeting["decisions"] = decisions
    meeting["action_items"] = tasks
    meeting["conflicts"] = conflicts
    return meeting


@router.post("/{meeting_id}/process")
def process_meeting(
    meeting_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    try:
        return orchestrator.process_meeting(
            conn=conn,
            meeting_id=meeting_id,
            organization_id=current_user["organization_id"],
            actor_user_id=current_user["user_id"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except AIProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
