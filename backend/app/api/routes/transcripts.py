import sqlite3
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.db.database import get_db, record_audit_log, utc_now
from app.schemas.schemas import SegmentUpdateRequest

router = APIRouter(tags=["Transcripts"])


@router.get("/api/meetings/{meeting_id}/transcript")
def get_meeting_transcript(
    meeting_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    transcript = conn.execute(
        "SELECT * FROM transcripts WHERE meeting_id = ? AND organization_id = ?",
        (meeting_id, current_user["organization_id"]),
    ).fetchone()
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found for this meeting.")

    segments = [
        dict(r)
        for r in conn.execute(
            """
            SELECT * FROM transcript_segments
            WHERE transcript_id = ? AND organization_id = ?
            ORDER BY segment_index ASC
            """,
            (transcript["id"], current_user["organization_id"]),
        ).fetchall()
    ]
    speakers = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM speakers WHERE meeting_id = ? AND organization_id = ?",
            (meeting_id, current_user["organization_id"]),
        ).fetchall()
    ]
    return {
        "transcript": dict(transcript),
        "speakers": speakers,
        "segments": segments,
    }


@router.patch("/api/transcripts/{transcript_id}/segments/{segment_id}")
def update_transcript_segment(
    transcript_id: str,
    segment_id: str,
    payload: SegmentUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    seg = conn.execute(
        """
        SELECT * FROM transcript_segments
        WHERE id = ? AND transcript_id = ? AND organization_id = ?
        """,
        (segment_id, transcript_id, current_user["organization_id"]),
    ).fetchone()
    if not seg:
        raise HTTPException(status_code=404, detail="Transcript segment not found.")

    now = utc_now()
    new_label = payload.speaker_label if payload.speaker_label is not None else seg["speaker_label"]
    new_text = payload.text if payload.text is not None else seg["text"]

    conn.execute(
        """
        UPDATE transcript_segments
        SET speaker_label = ?, text = ?, updated_at = ?
        WHERE id = ? AND organization_id = ?
        """,
        (new_label, new_text, now, segment_id, current_user["organization_id"]),
    )

    if payload.speaker_label is not None and seg["speaker_id"]:
        is_unknown = 1 if new_label.strip().lower() in {"unknown", "unknown speaker", ""} else 0
        conn.execute(
            """
            UPDATE speakers
            SET speaker_label = ?, mapped_user_id = COALESCE(?, mapped_user_id), is_unknown = ?, updated_at = ?
            WHERE id = ? AND organization_id = ?
            """,
            (new_label, payload.mapped_user_id, is_unknown, now, seg["speaker_id"], current_user["organization_id"]),
        )

    record_audit_log(
        conn,
        current_user["organization_id"],
        current_user["user_id"],
        "SPEAKER_SEGMENT_CORRECTED",
        "transcript_segment",
        segment_id,
        {"old_speaker": seg["speaker_label"], "new_speaker": new_label},
    )

    updated = dict(conn.execute("SELECT * FROM transcript_segments WHERE id = ?", (segment_id,)).fetchone())
    return updated
