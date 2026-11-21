import sqlite3
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.approvals.execution_service import ApprovalGateError, AuthorizedExecutionService
from app.db.database import get_db
from app.schemas.schemas import ApprovalEditRequest, ApprovalReviewRequest

router = APIRouter(prefix="/api/approvals", tags=["Approval Inbox"])
execution_service = AuthorizedExecutionService()


@router.get("")
def list_approvals(
    status: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    sql = "SELECT * FROM approvals WHERE organization_id = ?"
    params = [current_user["organization_id"]]
    if status:
        sql += " AND status = ?"
        params.append(status.upper())
    sql += " ORDER BY created_at DESC"
    rows = conn.execute(sql, params).fetchall()
    return {"approvals": [execution_service._format_approval(dict(r)) for r in rows]}


@router.get("/{approval_id}")
def get_approval(
    approval_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute(
        "SELECT * FROM approvals WHERE id = ? AND organization_id = ?",
        (approval_id, current_user["organization_id"]),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Approval record not found.")
    return execution_service._format_approval(dict(row))


@router.patch("/{approval_id}")
def edit_approval(
    approval_id: str,
    payload: ApprovalEditRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    try:
        return execution_service.edit_action(
            conn=conn,
            approval_id=approval_id,
            organization_id=current_user["organization_id"],
            editor_id=current_user["user_id"],
            new_content=payload.proposed_content,
            comment=payload.comment,
        )
    except ApprovalGateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post("/{approval_id}/approve")
def approve_action(
    approval_id: str,
    payload: Optional[ApprovalReviewRequest] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    body = payload or ApprovalReviewRequest()
    try:
        approved = execution_service.approve_action(
            conn=conn,
            approval_id=approval_id,
            organization_id=current_user["organization_id"],
            reviewer_id=current_user["user_id"],
            reviewer_role=current_user["role"],
            comment=body.comment,
        )
        if body.auto_execute:
            return execution_service.execute_approved_action(
                conn=conn,
                approval_id=approval_id,
                organization_id=current_user["organization_id"],
                executor_id=current_user["user_id"],
                executor_role=current_user["role"],
            )
        return approved
    except ApprovalGateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post("/{approval_id}/reject")
def reject_action(
    approval_id: str,
    payload: Optional[ApprovalReviewRequest] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    body = payload or ApprovalReviewRequest()
    try:
        return execution_service.reject_action(
            conn=conn,
            approval_id=approval_id,
            organization_id=current_user["organization_id"],
            reviewer_id=current_user["user_id"],
            reviewer_role=current_user["role"],
            comment=body.comment,
        )
    except ApprovalGateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post("/{approval_id}/execute")
def execute_approval(
    approval_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    try:
        return execution_service.execute_approved_action(
            conn=conn,
            approval_id=approval_id,
            organization_id=current_user["organization_id"],
            executor_id=current_user["user_id"],
            executor_role=current_user["role"],
        )
    except ApprovalGateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
