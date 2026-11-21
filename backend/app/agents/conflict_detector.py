import sqlite3
from typing import Any, Dict, List

from app.agents.memory import CrossMeetingMemoryAgent
from app.db.database import new_uuid, record_audit_log, utc_now


class ConflictDetectionAgent:
    """
    Agent 6: Conflict Detection.
    Compares new decisions/proposals against historical decisions retrieved from
    Cross-Meeting Decision Memory. Detects changed deadlines, contradictory statements,
    and superseded proposals. Never silently overwrites prior decisions.
    """

    def __init__(self) -> None:
        self.memory = CrossMeetingMemoryAgent()

    def detect_and_record_conflicts(
        self,
        conn: sqlite3.Connection,
        organization_id: str,
        actor_user_id: str,
        new_decision: Dict[str, Any],
        new_meeting_title: str,
    ) -> List[Dict[str, Any]]:
        query = f"{new_decision['subject']} {new_decision['statement']}"
        candidates = self.memory.search_decisions(
            conn=conn,
            organization_id=organization_id,
            query=query,
            top_k=5,
            exclude_meeting_id=new_decision["meeting_id"],
        )

        created_conflicts: List[Dict[str, Any]] = []
        new_val = (new_decision.get("key_value") or "").strip().lower()
        new_stmt = (new_decision.get("statement") or "").strip().lower()

        for old in candidates:
            if old["status"] in {"REJECTED", "SUPERSEDED"} or old["decision_type"] in {
                "PROPOSED",
                "UNRESOLVED",
            }:
                continue
            if new_decision["decision_type"] == "UNRESOLVED":
                continue

            same_subject = old["subject"].strip().lower() == new_decision["subject"].strip().lower()
            high_similarity = old["similarity_score"] >= 0.42
            if not (same_subject or high_similarity):
                continue

            old_val = (old.get("key_value") or "").strip().lower()
            old_stmt = (old.get("statement") or "").strip().lower()

            conflict_type = None
            severity = "MEDIUM"
            explanation = ""
            suggested_resolution = ""

            # Case 1: Changed deadline / date value on the same topic
            if old_val and new_val and old_val != new_val:
                conflict_type = "DEADLINE_CHANGE"
                severity = "HIGH"
                explanation = (
                    f"Conflict detected on '{old['subject']}': previously confirmed/recorded as "
                    f"'{old['key_value']}' in meeting '{old['meeting_title']}', while new meeting "
                    f"'{new_meeting_title}' introduces '{new_decision['key_value']}'."
                )
                suggested_resolution = (
                    f"Review both excerpts and have an authorized manager either keep '{old['key_value']}' "
                    f"or formally confirm updating the decision to '{new_decision['key_value']}'."
                )
            # Case 2: Opposing decision types (e.g. CONFIRMED vs REJECTED) or direct contradiction
            elif (
                (old["decision_type"] == "CONFIRMED" and new_decision["decision_type"] == "REJECTED")
                or (old["decision_type"] == "REJECTED" and new_decision["decision_type"] in {"CONFIRMED", "PROPOSED"})
                or (
                    same_subject
                    and old_stmt != new_stmt
                    and any(w in new_stmt for w in ("instead", "cancel", "delay", "push", "change", "replace", "move"))
                )
            ):
                conflict_type = "CONTRADICTION"
                severity = "HIGH"
                explanation = (
                    f"Potential contradiction on '{old['subject']}' between '{old['meeting_title']}' "
                    f"and '{new_meeting_title}'."
                )
                suggested_resolution = (
                    "Confirm with stakeholders whether the new statement supersedes the earlier decision."
                )

            if not conflict_type:
                continue

            now = utc_now()
            rel_id = new_uuid()
            conn.execute(
                """
                INSERT INTO decision_relationships (
                    id, organization_id, source_decision_id, target_decision_id,
                    relationship_type, similarity_score, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rel_id,
                    organization_id,
                    new_decision["id"],
                    old["id"],
                    "CONFLICTS_WITH",
                    old["similarity_score"],
                    now,
                ),
            )

            conflict_id = new_uuid()
            conn.execute(
                """
                INSERT INTO decision_conflicts (
                    id, organization_id, existing_decision_id, new_decision_id,
                    existing_meeting_id, new_meeting_id, conflict_type, severity,
                    explanation, suggested_resolution, existing_evidence, new_evidence,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
                """,
                (
                    conflict_id,
                    organization_id,
                    old["id"],
                    new_decision["id"],
                    old["meeting_id"],
                    new_decision["meeting_id"],
                    conflict_type,
                    severity,
                    explanation,
                    suggested_resolution,
                    old.get("evidence_quote") or old["statement"],
                    new_decision.get("evidence_quote") or new_decision["statement"],
                    now,
                    now,
                ),
            )

            record_audit_log(
                conn,
                organization_id,
                actor_user_id,
                "DECISION_CONFLICT_DETECTED",
                "decision_conflict",
                conflict_id,
                {
                    "existing_decision_id": old["id"],
                    "new_decision_id": new_decision["id"],
                    "conflict_type": conflict_type,
                },
            )

            created_conflicts.append(
                {
                    "id": conflict_id,
                    "existing_decision_id": old["id"],
                    "new_decision_id": new_decision["id"],
                    "existing_meeting_id": old["meeting_id"],
                    "existing_meeting_title": old["meeting_title"],
                    "new_meeting_id": new_decision["meeting_id"],
                    "new_meeting_title": new_meeting_title,
                    "conflict_type": conflict_type,
                    "severity": severity,
                    "explanation": explanation,
                    "suggested_resolution": suggested_resolution,
                    "existing_evidence": old.get("evidence_quote") or old["statement"],
                    "new_evidence": new_decision.get("evidence_quote") or new_decision["statement"],
                    "status": "OPEN",
                }
            )

        return created_conflicts
