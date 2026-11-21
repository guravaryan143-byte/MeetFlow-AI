import json
import sqlite3
from typing import Any, Dict, Optional

from app.core.security import compute_payload_hash, generate_idempotency_key
from app.db.database import new_uuid, record_audit_log, utc_now


class ActionPreparationService:
    """
    Agent 7 & Layer 4 (Preparation Side):
    Prepares proposed external actions (tasks, reminders, weekly digests, emails,
    calendar updates, decision publishing) as PENDING approval records.

    SECURITY BOUNDARY:
    This service has ZERO access to external integration adapters or credentials.
    It can ONLY create PENDING proposals in the approvals table.
    """

    def prepare_action(
        self,
        conn: sqlite3.Connection,
        organization_id: str,
        requested_by: str,
        action_type: str,
        target_provider: str,
        proposed_content: Dict[str, Any],
        source_meeting_id: Optional[str] = None,
        source_entity_id: Optional[str] = None,
        supporting_evidence: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = utc_now()
        approval_id = new_uuid()
        payload_hash = compute_payload_hash(proposed_content)
        idempotency_key = generate_idempotency_key(
            organization_id, action_type, target_provider, proposed_content
        )

        conn.execute(
            """
            INSERT INTO approvals (
                id, organization_id, action_type, target_provider,
                proposed_content_json, payload_hash, idempotency_key,
                source_meeting_id, source_entity_id, supporting_evidence,
                requested_by, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
            """,
            (
                approval_id,
                organization_id,
                action_type,
                target_provider,
                json.dumps(proposed_content, sort_keys=True, default=str),
                payload_hash,
                idempotency_key,
                source_meeting_id,
                source_entity_id,
                supporting_evidence,
                requested_by,
                now,
                now,
            ),
        )

        record_audit_log(
            conn,
            organization_id,
            requested_by,
            "APPROVAL_PROPOSED",
            "approval",
            approval_id,
            {
                "action_type": action_type,
                "target_provider": target_provider,
                "source_entity_id": source_entity_id,
                "status": "PENDING",
            },
        )

        return {
            "id": approval_id,
            "organization_id": organization_id,
            "action_type": action_type,
            "target_provider": target_provider,
            "proposed_content": proposed_content,
            "payload_hash": payload_hash,
            "idempotency_key": idempotency_key,
            "source_meeting_id": source_meeting_id,
            "source_entity_id": source_entity_id,
            "supporting_evidence": supporting_evidence,
            "requested_by": requested_by,
            "status": "PENDING",
            "created_at": now,
        }
