import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.agents.action_prep import ActionPreparationService
from app.db.database import new_uuid, record_audit_log, utc_now


def _parse_iso_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%B %d, %Y", "%B %d %Y"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


class ReportingAgent:
    """
    Agent 8: Reporting, Personalized Weekly Digests, Accountability Score & Commitment Radar.
    Computes all metrics strictly from persisted database records — never invented analytics.
    """

    def __init__(self) -> None:
        self.action_prep = ActionPreparationService()

    def generate_weekly_digest_for_user(
        self,
        conn: sqlite3.Connection,
        organization_id: str,
        target_user_id: str,
        requested_by: str,
        delivery_day: str = "Monday",
        delivery_time: str = "09:00",
        timezone_name: str = "UTC",
        digest_format: str = "markdown",
    ) -> Dict[str, Any]:
        user_row = conn.execute(
            "SELECT id, email, full_name, timezone FROM users WHERE id = ?",
            (target_user_id,),
        ).fetchone()
        if not user_row:
            raise ValueError("Target user not found.")

        now_dt = datetime.now(timezone.utc)
        period_end = now_dt.date().isoformat()
        period_start = (now_dt - timedelta(days=7)).date().isoformat()

        # Fetch tasks assigned ONLY to this user (by user_id or exact display name within org)
        tasks_rows = conn.execute(
            """
            SELECT * FROM action_items
            WHERE organization_id = ? AND is_deleted = 0
              AND (assigned_user_id = ? OR LOWER(COALESCE(assigned_name, '')) = LOWER(?))
            ORDER BY created_at DESC
            """,
            (organization_id, target_user_id, user_row["full_name"]),
        ).fetchall()

        assigned_tasks = [dict(r) for r in tasks_rows]
        completed_tasks = [t for t in assigned_tasks if t["status"] == "COMPLETED"]
        pending_tasks = [t for t in assigned_tasks if t["status"] in {"OPEN", "IN_PROGRESS", "BLOCKED"}]
        overdue_tasks = []
        upcoming_deadlines = []

        for t in pending_tasks:
            dt = _parse_iso_date(t.get("deadline"))
            if dt:
                if dt < now_dt:
                    overdue_tasks.append(t)
                elif dt <= now_dt + timedelta(days=7):
                    upcoming_deadlines.append(t)

        # Decisions involving this user
        decisions_rows = conn.execute(
            """
            SELECT d.*, m.title AS meeting_title
            FROM decisions d
            JOIN meetings m ON d.meeting_id = m.id
            WHERE d.organization_id = ? AND d.is_deleted = 0
            ORDER BY d.created_at DESC
            """,
            (organization_id,),
        ).fetchall()
        involving_decisions = []
        for r in decisions_rows:
            d = dict(r)
            parts = json.loads(d.get("participants_json") or "[]")
            if (
                d.get("confirmed_by") == target_user_id
                or any(user_row["full_name"].lower() in p.lower() for p in parts)
            ):
                involving_decisions.append(
                    {
                        "id": d["id"],
                        "subject": d["subject"],
                        "statement": d["statement"],
                        "status": d["status"],
                        "meeting_title": d["meeting_title"],
                    }
                )

        unresolved_commitments = [
            t for t in pending_tasks if t["status"] == "BLOCKED" or t in overdue_tasks
        ]

        # Compare against previous digest
        prev_row = conn.execute(
            """
            SELECT content_json FROM weekly_digests
            WHERE organization_id = ? AND user_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (organization_id, target_user_id),
        ).fetchone()
        prev_completed = 0
        if prev_row:
            prev_content = json.loads(prev_row["content_json"])
            prev_completed = len(prev_content.get("completed_tasks", []))
        changes_since_last = {
            "completed_delta": len(completed_tasks) - prev_completed,
            "new_pending_count": len(pending_tasks),
        }

        # Suggested next priorities (overdue first, then URGENT/HIGH)
        priority_order = {"URGENT": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        sorted_next = sorted(
            pending_tasks,
            key=lambda x: (0 if x in overdue_tasks else 1, priority_order.get(x["priority"], 2)),
        )[:3]

        digest_content = {
            "recipient_user_id": target_user_id,
            "recipient_name": user_row["full_name"],
            "recipient_email": user_row["email"],
            "period_start": period_start,
            "period_end": period_end,
            "assigned_tasks": assigned_tasks,
            "completed_tasks": completed_tasks,
            "pending_tasks": pending_tasks,
            "overdue_tasks": overdue_tasks,
            "upcoming_deadlines": upcoming_deadlines,
            "decisions_involving_user": involving_decisions,
            "unresolved_commitments": unresolved_commitments,
            "changes_since_previous_digest": changes_since_last,
            "suggested_next_priorities": [
                {"id": t["id"], "title": t["title"], "priority": t["priority"], "deadline": t["deadline"]}
                for t in sorted_next
            ],
        }

        digest_id = new_uuid()
        now = utc_now()

        # Prepare as PENDING approval — NEVER dispatched without explicit approval
        approval = self.action_prep.prepare_action(
            conn=conn,
            organization_id=organization_id,
            requested_by=requested_by,
            action_type="WEEKLY_DIGEST",
            target_provider="email",
            proposed_content={
                "digest_id": digest_id,
                "recipient_email": user_row["email"],
                "recipient_name": user_row["full_name"],
                "subject": f"MeetFlow AI Weekly Digest ({period_start} to {period_end})",
                "summary": {
                    "assigned": len(assigned_tasks),
                    "completed": len(completed_tasks),
                    "pending": len(pending_tasks),
                    "overdue": len(overdue_tasks),
                },
                "format": digest_format,
            },
            source_entity_id=digest_id,
            supporting_evidence=f"Generated from {len(assigned_tasks)} persisted task(s) for {user_row['full_name']}.",
        )

        conn.execute(
            """
            INSERT INTO weekly_digests (
                id, organization_id, user_id, period_start, period_end,
                delivery_day, delivery_time, timezone, digest_format,
                content_json, status, approval_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_APPROVAL', ?, ?, ?)
            """,
            (
                digest_id,
                organization_id,
                target_user_id,
                period_start,
                period_end,
                delivery_day,
                delivery_time,
                timezone_name,
                digest_format,
                json.dumps(digest_content, default=str),
                approval["id"],
                now,
                now,
            ),
        )

        record_audit_log(
            conn,
            organization_id,
            requested_by,
            "WEEKLY_DIGEST_GENERATED",
            "weekly_digest",
            digest_id,
            {"target_user_id": target_user_id, "approval_id": approval["id"]},
        )

        return {
            "id": digest_id,
            "user_id": target_user_id,
            "period_start": period_start,
            "period_end": period_end,
            "delivery_day": delivery_day,
            "delivery_time": delivery_time,
            "timezone": timezone_name,
            "digest_format": digest_format,
            "status": "PENDING_APPROVAL",
            "approval_id": approval["id"],
            "content": digest_content,
            "created_at": now,
        }

    def compute_analytics_overview(
        self, conn: sqlite3.Connection, organization_id: str
    ) -> Dict[str, Any]:
        now_dt = datetime.now(timezone.utc)
        meetings_count = conn.execute(
            "SELECT COUNT(*) AS count FROM meetings WHERE organization_id = ? AND is_deleted = 0",
            (organization_id,),
        ).fetchone()["count"]
        decisions_count = conn.execute(
            "SELECT COUNT(*) AS count FROM decisions WHERE organization_id = ? AND is_deleted = 0",
            (organization_id,),
        ).fetchone()["count"]
        open_conflicts = conn.execute(
            "SELECT COUNT(*) AS count FROM decision_conflicts WHERE organization_id = ? AND status = 'OPEN'",
            (organization_id,),
        ).fetchone()["count"]
        pending_approvals = conn.execute(
            "SELECT COUNT(*) AS count FROM approvals WHERE organization_id = ? AND status = 'PENDING'",
            (organization_id,),
        ).fetchone()["count"]

        tasks = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM action_items WHERE organization_id = ? AND is_deleted = 0",
                (organization_id,),
            ).fetchall()
        ]
        total_tasks = len(tasks)
        completed = sum(1 for t in tasks if t["status"] == "COMPLETED")
        pending = sum(1 for t in tasks if t["status"] in {"OPEN", "IN_PROGRESS", "BLOCKED"})
        overdue = 0
        for t in tasks:
            if t["status"] != "COMPLETED":
                dt = _parse_iso_date(t.get("deadline"))
                if dt and dt < now_dt:
                    overdue += 1

        completion_rate = round((completed / total_tasks) * 100.0, 1) if total_tasks > 0 else 0.0
        # Transparent Accountability Score backed strictly by database counts
        overdue_penalty = (overdue / total_tasks) * 25.0 if total_tasks > 0 else 0.0
        accountability_score = round(max(0.0, min(100.0, completion_rate - overdue_penalty + (20.0 if total_tasks > 0 else 0.0))), 1) if total_tasks > 0 else 0.0

        return {
            "meetings_count": meetings_count,
            "decisions_count": decisions_count,
            "open_conflicts_count": open_conflicts,
            "pending_approvals_count": pending_approvals,
            "tasks_summary": {
                "total": total_tasks,
                "completed": completed,
                "pending": pending,
                "overdue": overdue,
                "completion_rate_pct": completion_rate,
            },
            "accountability_score": {
                "score": accountability_score,
                "methodology": "Derived transparently from completed tasks, pending tasks, and overdue tasks in the database.",
                "underlying_data": {
                    "completed_tasks": completed,
                    "pending_tasks": pending,
                    "overdue_tasks": overdue,
                    "total_tasks": total_tasks,
                },
            },
        }

    def compute_commitment_radar(
        self, conn: sqlite3.Connection, organization_id: str
    ) -> Dict[str, Any]:
        now_dt = datetime.now(timezone.utc)
        tasks = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM action_items WHERE organization_id = ? AND is_deleted = 0 AND status != 'COMPLETED'",
                (organization_id,),
            ).fetchall()
        ]
        approaching = []
        delayed = []
        unresolved_deps = []
        at_risk = []

        for t in tasks:
            deps = json.loads(t.get("dependencies_json") or "[]")
            dt = _parse_iso_date(t.get("deadline"))
            if deps or t["status"] == "BLOCKED":
                unresolved_deps.append(t)
            if dt:
                if dt < now_dt:
                    delayed.append(t)
                    at_risk.append({"task": t, "reason": "Past deadline"})
                elif dt <= now_dt + timedelta(days=5):
                    approaching.append(t)
                    if t["priority"] in {"HIGH", "URGENT"}:
                        at_risk.append({"task": t, "reason": "High priority approaching deadline"})
            elif t["priority"] in {"HIGH", "URGENT"} and not t.get("assigned_name"):
                at_risk.append({"task": t, "reason": "High priority task with no owner"})

        open_conflicts = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM decision_conflicts WHERE organization_id = ? AND status = 'OPEN'",
                (organization_id,),
            ).fetchall()
        ]

        return {
            "approaching_deadlines": approaching,
            "delayed_tasks": delayed,
            "unresolved_dependencies": unresolved_deps,
            "open_conflicts": open_conflicts,
            "at_risk_commitments": at_risk,
        }
