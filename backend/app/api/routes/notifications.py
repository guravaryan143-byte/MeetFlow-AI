import hashlib
import json
import sqlite3
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.action_prep import ActionPreparationService
from app.agents.reporting import ReportingAgent
from app.api.deps import get_current_user
from app.db.database import get_db, new_uuid, record_audit_log, utc_now
from app.schemas.schemas import DigestGenerateRequest, ReminderScheduleRequest

router = APIRouter(tags=["Notifications, Reminders & Digests"])
action_prep = ActionPreparationService()
reporting_agent = ReportingAgent()


@router.get("/api/notifications")
def list_notifications(
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = conn.execute(
        """
        SELECT * FROM notifications
        WHERE organization_id = ? AND user_id = ?
        ORDER BY created_at DESC
        """,
        (current_user["organization_id"], current_user["user_id"]),
    ).fetchall()
    return {"notifications": [dict(r) for r in rows]}


@router.get("/api/reminders")
def list_reminders(
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = conn.execute(
        """
        SELECT r.*, a.title AS task_title, a.deadline AS task_deadline
        FROM reminders r
        JOIN action_items a ON r.action_item_id = a.id
        WHERE r.organization_id = ?
        ORDER BY r.created_at DESC
        """,
        (current_user["organization_id"],),
    ).fetchall()
    return {"reminders": [dict(r) for r in rows]}


@router.post("/api/reminders/schedule", status_code=status.HTTP_201_CREATED)
def schedule_reminder(
    payload: ReminderScheduleRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    task = conn.execute(
        "SELECT * FROM action_items WHERE id = ? AND organization_id = ? AND is_deleted = 0",
        (payload.action_item_id, current_user["organization_id"]),
    ).fetchone()
    if not task:
        raise HTTPException(status_code=404, detail="Action item not found.")

    scheduled_for = payload.scheduled_for or task["deadline"] or utc_now()
    dedup_raw = f"{current_user['organization_id']}:{task['id']}:{payload.reminder_type}:{scheduled_for}"
    dedup_key = hashlib.sha256(dedup_raw.encode("utf-8")).hexdigest()[:32]

    existing = conn.execute(
        "SELECT * FROM reminders WHERE dedup_key = ?", (dedup_key,)
    ).fetchone()
    if existing:
        return dict(existing)

    now = utc_now()
    reminder_id = new_uuid()

    # Prepare reminder as PENDING approval — never dispatched externally without approval
    approval = action_prep.prepare_action(
        conn=conn,
        organization_id=current_user["organization_id"],
        requested_by=current_user["user_id"],
        action_type="DEADLINE_REMINDER",
        target_provider=payload.target_provider,
        proposed_content={
            "reminder_id": reminder_id,
            "action_item_id": task["id"],
            "task_title": task["title"],
            "assigned_name": task["assigned_name"],
            "deadline": task["deadline"],
            "scheduled_for": scheduled_for,
            "reminder_type": payload.reminder_type,
            "timezone": payload.timezone,
            "subject": f"[{payload.reminder_type}] Deadline Reminder: {task['title']}",
        },
        source_meeting_id=task["meeting_id"],
        source_entity_id=reminder_id,
        supporting_evidence=task["evidence_quote"] or f"Scheduled reminder for '{task['title']}'",
    )

    conn.execute(
        """
        INSERT INTO reminders (
            id, organization_id, action_item_id, user_id, scheduled_for,
            reminder_type, timezone, status, approval_id, dedup_key,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING_APPROVAL', ?, ?, ?, ?)
        """,
        (
            reminder_id,
            current_user["organization_id"],
            task["id"],
            task["assigned_user_id"] or current_user["user_id"],
            scheduled_for,
            payload.reminder_type,
            payload.timezone,
            approval["id"],
            dedup_key,
            now,
            now,
        ),
    )

    record_audit_log(
        conn,
        current_user["organization_id"],
        current_user["user_id"],
        "REMINDER_SCHEDULED",
        "reminder",
        reminder_id,
        {"action_item_id": task["id"], "approval_id": approval["id"]},
    )

    row = dict(conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone())
    return row


@router.get("/api/digests")
def list_digests(
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = conn.execute(
        """
        SELECT * FROM weekly_digests
        WHERE organization_id = ?
        ORDER BY created_at DESC
        """,
        (current_user["organization_id"],),
    ).fetchall()
    digests = []
    for r in rows:
        item = dict(r)
        item["content"] = json.loads(item.pop("content_json") or "{}")
        digests.append(item)
    return {"digests": digests}


@router.post("/api/digests/generate", status_code=status.HTTP_201_CREATED)
def generate_digest(
    payload: DigestGenerateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    target_uid = payload.user_id or current_user["user_id"]
    # Verify target user belongs to the same organization
    member = conn.execute(
        "SELECT user_id FROM organization_memberships WHERE organization_id = ? AND user_id = ?",
        (current_user["organization_id"], target_uid),
    ).fetchone()
    if not member:
        raise HTTPException(status_code=404, detail="Target user not found in this organization.")

    return reporting_agent.generate_weekly_digest_for_user(
        conn=conn,
        organization_id=current_user["organization_id"],
        target_user_id=target_uid,
        requested_by=current_user["user_id"],
        delivery_day=payload.delivery_day,
        delivery_time=payload.delivery_time,
        timezone_name=payload.timezone,
        digest_format=payload.digest_format,
    )
