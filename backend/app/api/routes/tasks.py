import json
import sqlite3
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.action_prep import ActionPreparationService
from app.api.deps import get_current_user
from app.db.database import get_db, new_uuid, record_audit_log, utc_now
from app.schemas.schemas import PrepareTaskSyncRequest, TaskCreateRequest, TaskUpdateRequest

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])
action_prep = ActionPreparationService()


@router.get("")
def list_tasks(
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = conn.execute(
        """
        SELECT * FROM action_items
        WHERE organization_id = ? AND is_deleted = 0
        ORDER BY created_at DESC
        """,
        (current_user["organization_id"],),
    ).fetchall()
    tasks = []
    for r in rows:
        item = dict(r)
        item["dependencies"] = json.loads(item.pop("dependencies_json") or "[]")
        tasks.append(item)
    return {"tasks": tasks}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    if payload.meeting_id:
        meeting = conn.execute(
            "SELECT id FROM meetings WHERE id = ? AND organization_id = ? AND is_deleted = 0",
            (payload.meeting_id, current_user["organization_id"]),
        ).fetchone()
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found in this organization.")
    if payload.assigned_user_id:
        member = conn.execute(
            "SELECT user_id FROM organization_memberships WHERE organization_id = ? AND user_id = ?",
            (current_user["organization_id"], payload.assigned_user_id),
        ).fetchone()
        if not member:
            raise HTTPException(status_code=404, detail="Assigned user is not a member of this organization.")

    now = utc_now()
    task_id = new_uuid()
    conn.execute(
        """
        INSERT INTO action_items (
            id, organization_id, meeting_id, title, description,
            assigned_user_id, assigned_name, deadline, priority, status,
            dependencies_json, confidence, review_status, sync_status,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, 1.0, 'APPROVED', 'NOT_SYNCED', ?, ?)
        """,
        (
            task_id,
            current_user["organization_id"],
            payload.meeting_id,
            payload.title,
            payload.description,
            payload.assigned_user_id,
            payload.assigned_name,
            payload.deadline,
            payload.priority,
            json.dumps(payload.dependencies),
            now,
            now,
        ),
    )
    record_audit_log(
        conn,
        current_user["organization_id"],
        current_user["user_id"],
        "TASK_CREATED",
        "action_item",
        task_id,
        {"title": payload.title},
    )
    row = dict(conn.execute("SELECT * FROM action_items WHERE id = ?", (task_id,)).fetchone())
    row["dependencies"] = json.loads(row.pop("dependencies_json") or "[]")
    return row


@router.patch("/{task_id}")
def update_task(
    task_id: str,
    payload: TaskUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    existing = conn.execute(
        "SELECT * FROM action_items WHERE id = ? AND organization_id = ? AND is_deleted = 0",
        (task_id, current_user["organization_id"]),
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found.")

    updates = payload.model_dump(exclude_none=True)
    if not updates:
        row = dict(existing)
        row["dependencies"] = json.loads(row.pop("dependencies_json") or "[]")
        return row
    if updates.get("assigned_user_id"):
        member = conn.execute(
            "SELECT user_id FROM organization_memberships WHERE organization_id = ? AND user_id = ?",
            (current_user["organization_id"], updates["assigned_user_id"]),
        ).fetchone()
        if not member:
            raise HTTPException(status_code=404, detail="Assigned user is not a member of this organization.")

    updates["updated_at"] = utc_now()
    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [task_id, current_user["organization_id"]]
    conn.execute(f"UPDATE action_items SET {set_clause} WHERE id = ? AND organization_id = ?", values)

    record_audit_log(
        conn,
        current_user["organization_id"],
        current_user["user_id"],
        "TASK_UPDATED",
        "action_item",
        task_id,
        updates,
    )
    row = dict(conn.execute("SELECT * FROM action_items WHERE id = ?", (task_id,)).fetchone())
    row["dependencies"] = json.loads(row.pop("dependencies_json") or "[]")
    return row


@router.delete("/{task_id}")
def delete_task(
    task_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    existing = conn.execute(
        "SELECT id FROM action_items WHERE id = ? AND organization_id = ? AND is_deleted = 0",
        (task_id, current_user["organization_id"]),
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found.")

    conn.execute(
        "UPDATE action_items SET is_deleted = 1, updated_at = ? WHERE id = ? AND organization_id = ?",
        (utc_now(), task_id, current_user["organization_id"]),
    )
    record_audit_log(
        conn,
        current_user["organization_id"],
        current_user["user_id"],
        "TASK_DELETED",
        "action_item",
        task_id,
        {},
    )
    return {"deleted": True, "id": task_id}


@router.post("/{task_id}/prepare-sync", status_code=status.HTTP_201_CREATED)
def prepare_external_task_sync(
    task_id: str,
    payload: PrepareTaskSyncRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Prepare a PENDING approval for external tracker sync (Linear/Trello).
    Never executes externally until explicitly approved.
    """
    task = conn.execute(
        "SELECT * FROM action_items WHERE id = ? AND organization_id = ? AND is_deleted = 0",
        (task_id, current_user["organization_id"]),
    ).fetchone()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    return action_prep.prepare_action(
        conn=conn,
        organization_id=current_user["organization_id"],
        requested_by=current_user["user_id"],
        action_type=payload.action_type,
        target_provider=payload.provider,
        proposed_content={
            "task_id": task["id"],
            "title": task["title"],
            "description": task["description"],
            "assigned_user_id": task["assigned_user_id"],
            "assigned_name": task["assigned_name"],
            "deadline": task["deadline"],
            "priority": task["priority"],
        },
        source_meeting_id=task["meeting_id"],
        source_entity_id=task["id"],
        supporting_evidence=task["evidence_quote"] or f"Action item '{task['title']}'",
    )
