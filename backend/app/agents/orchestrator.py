import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.agents.action_prep import ActionPreparationService
from app.agents.conflict_detector import ConflictDetectionAgent
from app.agents.extractor import MeetingExtractionAgent
from app.agents.memory import compute_embedding
from app.agents.transcription import TranscriptionAgent
from app.db.database import new_uuid, record_audit_log, utc_now


class MeetingPipelineOrchestrator:
    """
    Observable multi-stage AI orchestration pipeline:
    Stage 1: Transcription & Speaker Attribution (Agent 1)
    Stage 2: Meeting Understanding, Decision & Task Extraction (Agents 2, 3, 4)
    Stage 3: Cross-Meeting Memory & Conflict Detection (Agents 5, 6)
    Stage 4: Action Preparation into PENDING Approvals (Agent 7 — no external execution)
    """

    def __init__(self) -> None:
        self.transcriber = TranscriptionAgent()
        self.extractor = MeetingExtractionAgent()
        self.conflict_detector = ConflictDetectionAgent()
        self.action_prep = ActionPreparationService()

    def process_meeting(
        self,
        conn: sqlite3.Connection,
        meeting_id: str,
        organization_id: str,
        actor_user_id: str,
    ) -> Dict[str, Any]:
        meeting = conn.execute(
            "SELECT * FROM meetings WHERE id = ? AND organization_id = ? AND is_deleted = 0",
            (meeting_id, organization_id),
        ).fetchone()
        if not meeting:
            raise ValueError("Meeting not found.")

        pipeline_log: List[Dict[str, Any]] = []
        now = utc_now()
        conn.execute(
            "UPDATE meetings SET status = 'PROCESSING', updated_at = ? WHERE id = ?",
            (now, meeting_id),
        )

        try:
            conn.execute("SAVEPOINT meetflow_processing")
            # --- STAGE 1: Transcription & Speaker Attribution ---
            transcript_row = conn.execute(
                "SELECT * FROM transcripts WHERE meeting_id = ?", (meeting_id,)
            ).fetchone()
            audio_path = Path(meeting["audio_file_path"]) if meeting["audio_file_path"] else None
            raw_text = transcript_row["raw_text"] if transcript_row else ""

            stage1_out = self.transcriber.transcribe_audio_or_text(
                raw_text=raw_text, audio_path=audio_path
            )
            if not transcript_row:
                transcript_id = new_uuid()
                conn.execute(
                    """
                    INSERT INTO transcripts (id, meeting_id, organization_id, raw_text, provider, language, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        transcript_id,
                        meeting_id,
                        organization_id,
                        stage1_out["raw_text"],
                        stage1_out["provider"],
                        stage1_out["language"],
                        now,
                        now,
                    ),
                )
            else:
                transcript_id = transcript_row["id"]

            # Clear any prior segments/speakers if re-processing
            conn.execute("DELETE FROM transcript_segments WHERE meeting_id = ?", (meeting_id,))
            conn.execute("DELETE FROM speakers WHERE meeting_id = ?", (meeting_id,))

            speaker_map: Dict[str, str] = {}
            segment_id_by_index: Dict[int, str] = {}

            # Load org users for optional name matching
            org_users = {
                r["full_name"].lower(): r["id"]
                for r in conn.execute(
                    """
                    SELECT u.id, u.full_name FROM users u
                    JOIN organization_memberships om ON u.id = om.user_id
                    WHERE om.organization_id = ?
                    """,
                    (organization_id,),
                ).fetchall()
            }

            for seg in stage1_out["segments"]:
                skey = seg["speaker_key"]
                if skey not in speaker_map:
                    sp_id = new_uuid()
                    mapped_uid = org_users.get(seg["speaker_label"].lower()) if not seg["is_unknown"] else None
                    conn.execute(
                        """
                        INSERT INTO speakers (id, organization_id, meeting_id, speaker_key, speaker_label, mapped_user_id, is_unknown, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            sp_id,
                            organization_id,
                            meeting_id,
                            skey,
                            seg["speaker_label"],
                            mapped_uid,
                            1 if seg["is_unknown"] else 0,
                            now,
                            now,
                        ),
                    )
                    speaker_map[skey] = sp_id

                seg_id = new_uuid()
                segment_id_by_index[seg["segment_index"]] = seg_id
                conn.execute(
                    """
                    INSERT INTO transcript_segments (
                        id, transcript_id, meeting_id, organization_id, speaker_id,
                        speaker_label, text, start_time, end_time, confidence, segment_index,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        seg_id,
                        transcript_id,
                        meeting_id,
                        organization_id,
                        speaker_map[skey],
                        seg["speaker_label"],
                        seg["text"],
                        seg["start_time"],
                        seg["end_time"],
                        seg["confidence"],
                        seg["segment_index"],
                        now,
                        now,
                    ),
                )

            pipeline_log.append(
                {
                    "stage": "transcription_and_speaker_attribution",
                    "status": "COMPLETED",
                    "segments_count": len(stage1_out["segments"]),
                    "speakers_count": len(speaker_map),
                }
            )

            # --- STAGE 2: Understanding, Decision & Task Extraction ---
            part_rows = conn.execute(
                "SELECT display_name FROM meeting_participants WHERE meeting_id = ?",
                (meeting_id,),
            ).fetchall()
            known_participants = [r["display_name"] for r in part_rows]

            understanding = self.extractor.extract(
                meeting_title=meeting["title"],
                segments=stage1_out["segments"],
                known_participants=known_participants,
            )

            persisted_decisions: List[Dict[str, Any]] = []
            all_conflicts: List[Dict[str, Any]] = []

            for dec in understanding.decisions:
                dec_id = new_uuid()
                source_seg_id = segment_id_by_index.get(dec.source_segment_index)
                emb = compute_embedding(f"{dec.subject} {dec.statement}")
                # New proposals NEVER auto-confirm; confirmed decisions without conflicts start CONFIRMED or PENDING_REVIEW
                initial_status = (
                    "CONFIRMED"
                    if (dec.decision_type == "CONFIRMED" and not dec.needs_review)
                    else ("REJECTED" if dec.decision_type == "REJECTED" else "PENDING_REVIEW")
                )
                conn.execute(
                    """
                    INSERT INTO decisions (
                        id, organization_id, meeting_id, source_segment_id, subject, statement,
                        decision_type, status, key_value, evidence_quote, participants_json,
                        confidence, needs_review, embedding_json, current_version,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        dec_id,
                        organization_id,
                        meeting_id,
                        source_seg_id,
                        dec.subject,
                        dec.statement,
                        dec.decision_type,
                        initial_status,
                        dec.key_value,
                        dec.evidence_quote,
                        json.dumps(dec.participants),
                        dec.confidence,
                        1 if dec.needs_review else 0,
                        json.dumps(emb),
                        now,
                        now,
                    ),
                )
                # Record initial Decision Version (v1) for Decision DNA
                conn.execute(
                    """
                    INSERT INTO decision_versions (
                        id, decision_id, organization_id, version_number, statement, key_value,
                        status, source_meeting_id, evidence_quote, changed_by, change_reason, created_at
                    ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, 'Initial extraction from meeting', ?)
                    """,
                    (
                        new_uuid(),
                        dec_id,
                        organization_id,
                        dec.statement,
                        dec.key_value,
                        initial_status,
                        meeting_id,
                        dec.evidence_quote,
                        actor_user_id,
                        now,
                    ),
                )

                dec_record = {
                    "id": dec_id,
                    "meeting_id": meeting_id,
                    "subject": dec.subject,
                    "statement": dec.statement,
                    "decision_type": dec.decision_type,
                    "status": initial_status,
                    "key_value": dec.key_value,
                    "evidence_quote": dec.evidence_quote,
                    "source_segment_id": source_seg_id,
                    "confidence": dec.confidence,
                    "needs_review": dec.needs_review,
                }
                persisted_decisions.append(dec_record)

                # --- STAGE 3: Cross-Meeting Memory & Conflict Detection ---
                conflicts = self.conflict_detector.detect_and_record_conflicts(
                    conn=conn,
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    new_decision=dec_record,
                    new_meeting_title=meeting["title"],
                )
                if conflicts:
                    # If conflict detected, never auto-confirm — force PENDING_REVIEW
                    conn.execute(
                        "UPDATE decisions SET status = 'PENDING_REVIEW', needs_review = 1, updated_at = ? WHERE id = ?",
                        (now, dec_id),
                    )
                    dec_record["status"] = "PENDING_REVIEW"
                    dec_record["needs_review"] = True
                    all_conflicts.extend(conflicts)

            persisted_tasks: List[Dict[str, Any]] = []
            prepared_approvals: List[Dict[str, Any]] = []

            for item in understanding.action_items:
                task_id = new_uuid()
                source_seg_id = segment_id_by_index.get(item.source_segment_index)
                assigned_uid = org_users.get(item.assigned_name.lower()) if item.assigned_name else None
                review_status = "NEEDS_REVIEW" if item.needs_review else "APPROVED"

                conn.execute(
                    """
                    INSERT INTO action_items (
                        id, organization_id, meeting_id, source_segment_id, title, description,
                        assigned_user_id, assigned_name, deadline, priority, status,
                        dependencies_json, evidence_quote, confidence, review_status,
                        sync_status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, 'NOT_SYNCED', ?, ?)
                    """,
                    (
                        task_id,
                        organization_id,
                        meeting_id,
                        source_seg_id,
                        item.title,
                        item.description,
                        assigned_uid,
                        item.assigned_name,
                        item.deadline,
                        item.priority,
                        json.dumps(item.dependencies),
                        item.evidence_quote,
                        item.confidence,
                        review_status,
                        now,
                        now,
                    ),
                )
                persisted_tasks.append(
                    {
                        "id": task_id,
                        "title": item.title,
                        "assigned_name": item.assigned_name,
                        "deadline": item.deadline,
                        "priority": item.priority,
                        "review_status": review_status,
                        "source_segment_id": source_seg_id,
                        "evidence_quote": item.evidence_quote,
                    }
                )

                # --- STAGE 4: Action Preparation (PENDING approval only, never executed) ---
                approval = self.action_prep.prepare_action(
                    conn=conn,
                    organization_id=organization_id,
                    requested_by=actor_user_id,
                    action_type="EXTERNAL_TASK_CREATE",
                    target_provider="linear",
                    proposed_content={
                        "task_id": task_id,
                        "title": item.title,
                        "description": item.description,
                        "assigned_name": item.assigned_name,
                        "assigned_user_id": assigned_uid,
                        "deadline": item.deadline,
                        "priority": item.priority,
                    },
                    source_meeting_id=meeting_id,
                    source_entity_id=task_id,
                    supporting_evidence=item.evidence_quote,
                )
                prepared_approvals.append(approval)

            pipeline_log.extend(
                [
                    {
                        "stage": "meeting_understanding_and_extraction",
                        "status": "COMPLETED",
                        "decisions_extracted": len(persisted_decisions),
                        "tasks_extracted": len(persisted_tasks),
                        "ai_usage": self.extractor.last_usage,
                    },
                    {
                        "stage": "cross_meeting_memory_and_conflict_detection",
                        "status": "COMPLETED",
                        "conflicts_detected": len(all_conflicts),
                    },
                    {
                        "stage": "action_preparation",
                        "status": "COMPLETED",
                        "pending_approvals_created": len(prepared_approvals),
                    },
                ]
            )

            done_at = utc_now()
            conn.execute(
                """
                UPDATE meetings
                SET summary = ?, topics_json = ?, pipeline_log_json = ?, status = 'PROCESSED', updated_at = ?
                WHERE id = ?
                """,
                (
                    understanding.summary,
                    json.dumps(understanding.topics),
                    json.dumps(pipeline_log),
                    done_at,
                    meeting_id,
                ),
            )

            record_audit_log(
                conn,
                organization_id,
                actor_user_id,
                "MEETING_PROCESSED",
                "meeting",
                meeting_id,
                {
                    "decisions": len(persisted_decisions),
                    "tasks": len(persisted_tasks),
                    "conflicts": len(all_conflicts),
                    "pending_approvals": len(prepared_approvals),
                },
            )

            conn.execute("RELEASE SAVEPOINT meetflow_processing")
            return {
                "meeting_id": meeting_id,
                "status": "PROCESSED",
                "summary": understanding.summary,
                "topics": understanding.topics,
                "participants": understanding.participants,
                "decisions": persisted_decisions,
                "action_items": persisted_tasks,
                "conflicts": all_conflicts,
                "pending_approvals": prepared_approvals,
                "pipeline_log": pipeline_log,
            }

        except Exception as exc:
            try:
                conn.execute("ROLLBACK TO SAVEPOINT meetflow_processing")
                conn.execute("RELEASE SAVEPOINT meetflow_processing")
            except Exception:
                conn.rollback()
            pipeline_log.append({"stage": "error", "status": "FAILED", "error": str(exc)})
            conn.execute(
                "UPDATE meetings SET status = 'FAILED', pipeline_log_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(pipeline_log), utc_now(), meeting_id),
            )
            conn.commit()
            raise
