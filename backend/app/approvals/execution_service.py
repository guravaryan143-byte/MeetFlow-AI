import json
import sqlite3
from typing import Any, Dict, Optional

from app.core.security import compute_payload_hash
from app.db.database import new_uuid, record_audit_log, utc_now
from app.integrations.adapters import get_adapter

AUTHORIZED_APPROVER_ROLES = {"ADMIN", "MANAGER"}


class ApprovalGateError(Exception):
    def __init__(self, message: str, status_code: int = 403):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AuthorizedExecutionService:
    """
    Layer 4 — Strictly Isolated Authorized Execution Service.
    THE ONLY SERVICE IN MEETFLOW AI PERMITTED TO CALL EXTERNAL INTEGRATION ADAPTERS.

    Mandatory backend enforcement:
    1. Only APPROVED actions can be executed (PENDING/REJECTED/CANCELLED are blocked).
    2. Only ADMIN or MANAGER members of the same organization can approve or execute.
    3. Payload SHA-256 hash is re-verified before execution to prevent tampering.
    4. Editing an approved action automatically invalidates approval back to PENDING.
    5. Retrying an already-executed action returns the existing execution record (idempotency).
    6. Every transition and execution is recorded in audit_logs and external_execution_records.
    """

    def approve_action(
        self,
        conn: sqlite3.Connection,
        approval_id: str,
        organization_id: str,
        reviewer_id: str,
        reviewer_role: str,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        if reviewer_role not in AUTHORIZED_APPROVER_ROLES:
            raise ApprovalGateError(
                "Unauthorized: only ADMIN or MANAGER roles can approve external actions.",
                status_code=403,
            )

        row = conn.execute(
            "SELECT * FROM approvals WHERE id = ? AND organization_id = ?",
            (approval_id, organization_id),
        ).fetchone()
        if not row:
            raise ApprovalGateError("Approval record not found in this organization.", status_code=404)

        if row["status"] != "PENDING":
            raise ApprovalGateError(
                f"Cannot approve action in state '{row['status']}'. Only PENDING actions can be approved.",
                status_code=409,
            )

        now = utc_now()
        conn.execute(
            """
            UPDATE approvals
            SET status = 'APPROVED', reviewer_id = ?, reviewed_at = ?, review_comment = ?, updated_at = ?
            WHERE id = ? AND organization_id = ?
            """,
            (reviewer_id, now, comment, now, approval_id, organization_id),
        )

        record_audit_log(
            conn,
            organization_id,
            reviewer_id,
            "APPROVAL_GRANTED",
            "approval",
            approval_id,
            {"action_type": row["action_type"], "comment": comment},
        )

        updated = dict(conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone())
        return self._format_approval(updated)

    def reject_action(
        self,
        conn: sqlite3.Connection,
        approval_id: str,
        organization_id: str,
        reviewer_id: str,
        reviewer_role: str,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        if reviewer_role not in AUTHORIZED_APPROVER_ROLES:
            raise ApprovalGateError(
                "Unauthorized: only ADMIN or MANAGER roles can reject external actions.",
                status_code=403,
            )

        row = conn.execute(
            "SELECT * FROM approvals WHERE id = ? AND organization_id = ?",
            (approval_id, organization_id),
        ).fetchone()
        if not row:
            raise ApprovalGateError("Approval record not found in this organization.", status_code=404)

        if row["status"] not in {"PENDING", "APPROVED"}:
            raise ApprovalGateError(
                f"Cannot reject action in state '{row['status']}'.",
                status_code=409,
            )

        now = utc_now()
        conn.execute(
            """
            UPDATE approvals
            SET status = 'REJECTED', reviewer_id = ?, reviewed_at = ?, review_comment = ?, updated_at = ?
            WHERE id = ? AND organization_id = ?
            """,
            (reviewer_id, now, comment, now, approval_id, organization_id),
        )

        # Update linked digest or reminder if applicable
        if row["action_type"] == "WEEKLY_DIGEST" and row["source_entity_id"]:
            conn.execute(
                "UPDATE weekly_digests SET status = 'REJECTED', updated_at = ? WHERE id = ?",
                (now, row["source_entity_id"]),
            )
        elif row["action_type"] == "DEADLINE_REMINDER" and row["source_entity_id"]:
            conn.execute(
                "UPDATE reminders SET status = 'CANCELLED', updated_at = ? WHERE id = ?",
                (now, row["source_entity_id"]),
            )

        record_audit_log(
            conn,
            organization_id,
            reviewer_id,
            "APPROVAL_REJECTED",
            "approval",
            approval_id,
            {"action_type": row["action_type"], "comment": comment},
        )

        updated = dict(conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone())
        return self._format_approval(updated)

    def edit_action(
        self,
        conn: sqlite3.Connection,
        approval_id: str,
        organization_id: str,
        editor_id: str,
        new_content: Dict[str, Any],
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Editing an APPROVED action MUST invalidate the prior approval and return it to PENDING.
        """
        row = conn.execute(
            "SELECT * FROM approvals WHERE id = ? AND organization_id = ?",
            (approval_id, organization_id),
        ).fetchone()
        if not row:
            raise ApprovalGateError("Approval record not found.", status_code=404)

        if row["status"] in {"EXECUTING", "EXECUTED"}:
            raise ApprovalGateError("Cannot edit an action that is executing or already executed.", status_code=409)

        now = utc_now()
        new_hash = compute_payload_hash(new_content)
        previous_status = row["status"]

        conn.execute(
            """
            UPDATE approvals
            SET proposed_content_json = ?, payload_hash = ?, status = 'PENDING',
                reviewer_id = NULL, reviewed_at = NULL, review_comment = ?, updated_at = ?
            WHERE id = ? AND organization_id = ?
            """,
            (
                json.dumps(new_content, sort_keys=True, default=str),
                new_hash,
                comment,
                now,
                approval_id,
                organization_id,
            ),
        )

        record_audit_log(
            conn,
            organization_id,
            editor_id,
            "APPROVAL_EDITED_INVALIDATED" if previous_status == "APPROVED" else "APPROVAL_EDITED",
            "approval",
            approval_id,
            {"previous_status": previous_status, "new_status": "PENDING"},
        )

        updated = dict(conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone())
        return self._format_approval(updated)

    def execute_approved_action(
        self,
        conn: sqlite3.Connection,
        approval_id: str,
        organization_id: str,
        executor_id: str,
        executor_role: str,
    ) -> Dict[str, Any]:
        """
        Validate all security invariants and dispatch via the target integration adapter.
        """
        if executor_role not in AUTHORIZED_APPROVER_ROLES:
            raise ApprovalGateError(
                "Unauthorized: only ADMIN or MANAGER roles can trigger external execution.",
                status_code=403,
            )

        row = conn.execute(
            "SELECT * FROM approvals WHERE id = ? AND organization_id = ?",
            (approval_id, organization_id),
        ).fetchone()
        if not row:
            raise ApprovalGateError("Approval record not found in this organization.", status_code=404)

        # Idempotency check: if already executed, return existing record without duplicating external call
        existing_exec = conn.execute(
            "SELECT * FROM external_execution_records WHERE idempotency_key = ? AND organization_id = ?",
            (row["idempotency_key"], organization_id),
        ).fetchone()
        if existing_exec and existing_exec["status"] == "SUCCESS":
            record_audit_log(
                conn,
                organization_id,
                executor_id,
                "EXTERNAL_EXECUTION_IDEMPOTENT_HIT",
                "approval",
                approval_id,
                {"execution_record_id": existing_exec["id"]},
            )
            return {
                "approval": self._format_approval(dict(row)),
                "execution_record": {
                    "id": existing_exec["id"],
                    "provider": existing_exec["provider"],
                    "external_reference_id": existing_exec["external_reference_id"],
                    "status": existing_exec["status"],
                    "idempotent_replay": True,
                    "response": json.loads(existing_exec["response_payload_json"] or "{}"),
                },
            }

        # Strict backend approval gate enforcement
        if row["status"] != "APPROVED":
            record_audit_log(
                conn,
                organization_id,
                executor_id,
                "EXTERNAL_EXECUTION_BLOCKED",
                "approval",
                approval_id,
                {"reason": f"Approval status is '{row['status']}', not 'APPROVED'"},
            )
            conn.commit()
            raise ApprovalGateError(
                f"Execution blocked by Approval Gate: action status is '{row['status']}'. Explicit APPROVED status is required.",
                status_code=403,
            )

        if not row["reviewer_id"]:
            raise ApprovalGateError("Execution blocked: missing verified reviewer identity.", status_code=403)

        # Payload integrity verification (blocks tampered payloads)
        payload = json.loads(row["proposed_content_json"])
        recomputed_hash = compute_payload_hash(payload)
        if recomputed_hash != row["payload_hash"]:
            record_audit_log(
                conn,
                organization_id,
                executor_id,
                "EXTERNAL_EXECUTION_TAMPER_BLOCKED",
                "approval",
                approval_id,
                {"expected_hash": row["payload_hash"], "actual_hash": recomputed_hash},
            )
            conn.commit()
            raise ApprovalGateError(
                "Execution blocked: payload integrity check failed (payload hash mismatch).",
                status_code=409,
            )

        # Claim the approval atomically so concurrent requests cannot dispatch twice.
        now = utc_now()
        claim = conn.execute(
            """
            UPDATE approvals SET status = 'EXECUTING', updated_at = ?
            WHERE id = ? AND organization_id = ? AND status = 'APPROVED'
            """,
            (now, approval_id, organization_id),
        )
        if claim.rowcount != 1:
            raise ApprovalGateError(
                "Execution could not claim this approval; refresh and verify its current status.",
                status_code=409,
            )

        # Fetch optional integration connection config
        conn_row = conn.execute(
            "SELECT * FROM integration_connections WHERE organization_id = ? AND provider = ?",
            (organization_id, row["target_provider"]),
        ).fetchone()
        connection_config = (
            {
                "workspace_name": conn_row["workspace_name"],
                "project_id": conn_row["project_id"],
                **json.loads(conn_row["config_json"] or "{}"),
            }
            if conn_row
            else {}
        )

        try:
            adapter = get_adapter(row["target_provider"])
            adapter_result = adapter.execute(
                action_type=row["action_type"],
                payload=payload,
                idempotency_key=row["idempotency_key"],
                connection_config=connection_config,
            )
            exec_id = new_uuid()
            done_at = utc_now()

            conn.execute(
                """
                INSERT INTO external_execution_records (
                    id, organization_id, approval_id, provider, idempotency_key,
                    external_reference_id, request_payload_json, response_payload_json,
                    status, attempt_count, executed_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'SUCCESS', 1, ?, ?)
                """,
                (
                    exec_id,
                    organization_id,
                    approval_id,
                    row["target_provider"],
                    row["idempotency_key"],
                    adapter_result.get("external_reference_id"),
                    row["proposed_content_json"],
                    json.dumps(adapter_result, default=str),
                    executor_id,
                    done_at,
                ),
            )

            conn.execute(
                """
                UPDATE approvals
                SET status = 'EXECUTED', executed_at = ?, execution_error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (done_at, done_at, approval_id),
            )

            # Propagate sync state back to linked entity
            if row["action_type"] in {"EXTERNAL_TASK_CREATE", "EXTERNAL_TASK_UPDATE"} and row["source_entity_id"]:
                conn.execute(
                    """
                    UPDATE action_items
                    SET external_provider = ?, external_task_id = ?, sync_status = 'SYNCED', updated_at = ?
                    WHERE id = ? AND organization_id = ?
                    """,
                    (
                        row["target_provider"],
                        adapter_result.get("external_reference_id"),
                        done_at,
                        row["source_entity_id"],
                        organization_id,
                    ),
                )
            elif row["action_type"] == "DEADLINE_REMINDER" and row["source_entity_id"]:
                conn.execute(
                    "UPDATE reminders SET status = 'SENT', updated_at = ? WHERE id = ? AND organization_id = ?",
                    (done_at, row["source_entity_id"], organization_id),
                )
            elif row["action_type"] == "WEEKLY_DIGEST" and row["source_entity_id"]:
                conn.execute(
                    "UPDATE weekly_digests SET status = 'SENT', updated_at = ? WHERE id = ? AND organization_id = ?",
                    (done_at, row["source_entity_id"], organization_id),
                )

            record_audit_log(
                conn,
                organization_id,
                executor_id,
                "EXTERNAL_EXECUTION_SUCCEEDED",
                "approval",
                approval_id,
                {
                    "provider": row["target_provider"],
                    "external_reference_id": adapter_result.get("external_reference_id"),
                    "execution_record_id": exec_id,
                },
            )

            updated = dict(conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone())
            return {
                "approval": self._format_approval(updated),
                "execution_record": {
                    "id": exec_id,
                    "provider": row["target_provider"],
                    "external_reference_id": adapter_result.get("external_reference_id"),
                    "status": "SUCCESS",
                    "idempotent_replay": False,
                    "response": adapter_result,
                },
            }

        except Exception as exc:
            err_at = utc_now()
            conn.execute(
                "UPDATE approvals SET status = 'FAILED', execution_error = ?, updated_at = ? WHERE id = ?",
                (str(exc), err_at, approval_id),
            )
            record_audit_log(
                conn,
                organization_id,
                executor_id,
                "EXTERNAL_EXECUTION_FAILED",
                "approval",
                approval_id,
                {"error": str(exc)},
            )
            conn.commit()
            raise ApprovalGateError(f"External execution failed: {exc}", status_code=502)

    @staticmethod
    def _format_approval(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "organization_id": row["organization_id"],
            "action_type": row["action_type"],
            "target_provider": row["target_provider"],
            "proposed_content": json.loads(row["proposed_content_json"]),
            "payload_hash": row["payload_hash"],
            "idempotency_key": row["idempotency_key"],
            "source_meeting_id": row["source_meeting_id"],
            "source_entity_id": row["source_entity_id"],
            "supporting_evidence": row["supporting_evidence"],
            "requested_by": row["requested_by"],
            "status": row["status"],
            "reviewer_id": row["reviewer_id"],
            "reviewed_at": row["reviewed_at"],
            "review_comment": row["review_comment"],
            "execution_error": row["execution_error"],
            "executed_at": row["executed_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
