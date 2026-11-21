import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Point DATABASE_URL to a dedicated isolated test database before importing app
_TEST_DB_DIR = tempfile.TemporaryDirectory()
_TEST_DB_URL = f"sqlite:///{Path(_TEST_DB_DIR.name) / 'test_meetflow.db'}"
os.environ["DATABASE_URL"] = _TEST_DB_URL
os.environ["UPLOAD_DIR"] = str(Path(_TEST_DB_DIR.name) / "uploads")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from app.core.config import settings  # noqa: E402

# Other test modules may import settings before this module is loaded.
settings.DATABASE_URL = _TEST_DB_URL

from app.db.database import db  # noqa: E402
from app.main import app  # noqa: E402


class MeetFlowWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        db.init_db()
        cls.client = TestClient(app)

    def _register(self, email: str, name: str, password: str = "StrongPass123!", org_name=None, org_id=None, role="ADMIN"):
        payload = {
            "email": email,
            "full_name": name,
            "password": password,
        }
        if org_name:
            payload["organization_name"] = org_name
        res = self.client.post("/api/auth/register", json=payload)
        self.assertEqual(res.status_code, 201, res.text)
        auth = res.json()
        if org_id:
            with db.transaction() as conn:
                conn.execute(
                    "DELETE FROM organization_memberships WHERE user_id = ?",
                    (auth["user"]["id"],),
                )
                conn.execute(
                    "DELETE FROM organizations WHERE id = ?",
                    (auth["organization"]["id"],),
                )
                conn.execute(
                    """
                    INSERT INTO organization_memberships (id, organization_id, user_id, role, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        f"test-membership-{auth['user']['id']}",
                        org_id,
                        auth["user"]["id"],
                        role,
                        "2026-01-01T00:00:00+00:00",
                    ),
                )
            login = self.client.post(
                "/api/auth/login",
                json={"email": email, "password": password},
            )
            self.assertEqual(login.status_code, 200, login.text)
            return login.json()
        return auth

    def _headers(self, token: str):
        return {"Authorization": f"Bearer {token}"}

    # ------------------------------------------------------------------
    # WORKFLOW A: Meeting Processing, Speaker Attribution & Correction
    # ------------------------------------------------------------------
    def test_workflow_a_meeting_processing_and_speaker_correction(self):
        auth = self._register("test-user-02@example.test", "Alice Chen", org_name="Acme Corp")
        headers = self._headers(auth["access_token"])

        transcript = (
            "[00:00:05] Alice Chen: Welcome everyone. The product launch date is confirmed as December 10.\n"
            "[00:00:22] Unknown: Bob will prepare the security checklist by December 5, high priority.\n"
            "[00:00:45] Bob Patel: I will update the onboarding docs after the API freeze.\n"
        )
        create_res = self.client.post(
            "/api/meetings",
            json={
                "title": "Q4 Launch Alignment",
                "meeting_date": "2026-11-20",
                "transcript_text": transcript,
                "participants": ["Alice Chen", "Bob Patel"],
            },
            headers=headers,
        )
        self.assertEqual(create_res.status_code, 201)
        meeting_id = create_res.json()["id"]

        proc_res = self.client.post(f"/api/meetings/{meeting_id}/process", headers=headers)
        self.assertEqual(proc_res.status_code, 200, proc_res.text)
        proc = proc_res.json()
        self.assertEqual(proc["status"], "PROCESSED")
        self.assertGreaterEqual(len(proc["decisions"]), 1)
        self.assertGreaterEqual(len(proc["action_items"]), 2)
        self.assertEqual(len(proc["pending_approvals"]), len(proc["action_items"]))

        # Verify transcript segments and unknown speaker preserved (never fabricated)
        tr_res = self.client.get(f"/api/meetings/{meeting_id}/transcript", headers=headers)
        self.assertEqual(tr_res.status_code, 200)
        tr_data = tr_res.json()
        self.assertEqual(len(tr_data["segments"]), 3)
        unknown_seg = tr_data["segments"][1]
        self.assertEqual(unknown_seg["speaker_label"], "Unknown Speaker")

        # Manually correct speaker identity
        patch_res = self.client.patch(
            f"/api/transcripts/{tr_data['transcript']['id']}/segments/{unknown_seg['id']}",
            json={"speaker_label": "Carol Diaz"},
            headers=headers,
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.json()["speaker_label"], "Carol Diaz")

        # Verify persisted meeting details include decisions & tasks with source evidence
        detail_res = self.client.get(f"/api/meetings/{meeting_id}", headers=headers)
        self.assertEqual(detail_res.status_code, 200)
        detail = detail_res.json()
        self.assertTrue(all(d["source_segment_id"] for d in detail["decisions"]))
        self.assertTrue(all(t["evidence_quote"] for t in detail["action_items"]))

    # ------------------------------------------------------------------
    # WORKFLOW B: Cross-Meeting Decision Memory & Conflict Detection
    # ------------------------------------------------------------------
    def test_workflow_b_cross_meeting_conflict_and_version_preservation(self):
        auth = self._register("test-user-03@example.test", "Maya Lin", org_name="Beta Labs")
        headers = self._headers(auth["access_token"])

        # Meeting A: Confirmed December 10 launch
        m1 = self.client.post(
            "/api/meetings",
            json={
                "title": "Meeting A - Launch Lock",
                "meeting_date": "2026-11-10",
                "transcript_text": "[00:01:00] Maya Lin: The product launch date is confirmed as December 10.",
            },
            headers=headers,
        ).json()
        p1 = self.client.post(f"/api/meetings/{m1['id']}/process", headers=headers).json()
        dec_a_id = p1["decisions"][0]["id"]
        self.assertEqual(p1["decisions"][0]["key_value"], "December 10")
        self.assertEqual(p1["decisions"][0]["status"], "CONFIRMED")

        # Meeting B: Proposes December 15
        m2 = self.client.post(
            "/api/meetings",
            json={
                "title": "Meeting B - Engineering Sync",
                "meeting_date": "2026-11-18",
                "transcript_text": "[00:02:10] Samira Rao: I propose moving the product launch date to December 15.",
            },
            headers=headers,
        ).json()
        p2 = self.client.post(f"/api/meetings/{m2['id']}/process", headers=headers).json()
        dec_b = p2["decisions"][0]
        self.assertEqual(dec_b["status"], "PENDING_REVIEW")  # Never auto-confirmed
        self.assertEqual(len(p2["conflicts"]), 1)

        conflict = p2["conflicts"][0]
        self.assertEqual(conflict["conflict_type"], "DEADLINE_CHANGE")
        self.assertEqual(conflict["existing_meeting_id"], m1["id"])
        self.assertEqual(conflict["new_meeting_id"], m2["id"])
        self.assertIn("December 10", conflict["existing_evidence"])
        self.assertIn("December 15", conflict["new_evidence"])

        # Verify conflict endpoint lists both meetings
        c_list = self.client.get("/api/decisions/conflicts", headers=headers).json()["conflicts"]
        self.assertEqual(len(c_list), 1)
        self.assertEqual(c_list[0]["status"], "OPEN")

        # Confirm updated decision via authorized manager -> preserves historical decision as SUPERSEDED
        confirm_res = self.client.post(
            f"/api/decisions/{dec_b['id']}/confirm",
            json={
                "conflict_id": conflict["id"],
                "resolution_action": "ADOPT_NEW",
                "change_reason": "QA needs 5 extra days for load testing",
            },
            headers=headers,
        )
        self.assertEqual(confirm_res.status_code, 200)
        self.assertEqual(confirm_res.json()["status"], "CONFIRMED")
        self.assertEqual(len(confirm_res.json()["versions"]), 2)

        # Verify historical Decision A is preserved (SUPERSEDED, never deleted/overwritten)
        old_dec = self.client.get(f"/api/decisions/{dec_a_id}", headers=headers).json()
        self.assertEqual(old_dec["status"], "SUPERSEDED")
        self.assertEqual(len(old_dec["versions"]), 2)

        # Verify semantic memory search retrieves both
        mem_res = self.client.post("/api/memory/search", json={"query": "product launch date"}, headers=headers)
        self.assertEqual(mem_res.status_code, 200)
        self.assertGreaterEqual(len(mem_res.json()["results"]), 2)

    def test_proposal_to_proposal_change_does_not_create_false_conflict(self):
        auth = self._register("test-user-04@example.test", "Dana Wu", org_name="Proposal Workspace")
        headers = self._headers(auth["access_token"])
        first = self.client.post(
            "/api/meetings",
            json={
                "title": "Initial Proposal",
                "transcript_text": "[00:00:10] Dana Wu: I propose moving the product launch date to December 10.",
            },
            headers=headers,
        ).json()
        self.assertEqual(
            self.client.post(f"/api/meetings/{first['id']}/process", headers=headers).status_code,
            200,
        )
        second = self.client.post(
            "/api/meetings",
            json={
                "title": "Revised Proposal",
                "transcript_text": "[00:00:10] Dana Wu: I propose moving the product launch date to December 15.",
            },
            headers=headers,
        ).json()
        processed = self.client.post(f"/api/meetings/{second['id']}/process", headers=headers)
        self.assertEqual(processed.status_code, 200, processed.text)
        self.assertEqual(processed.json()["conflicts"], [])
        self.assertEqual(processed.json()["decisions"][0]["decision_type"], "PROPOSED")

    def test_ai_provider_failure_marks_meeting_failed_without_partial_segments(self):
        auth = self._register("test-user-05@example.test", "Riley Park", org_name="Provider Workspace")
        headers = self._headers(auth["access_token"])
        meeting = self.client.post(
            "/api/meetings",
            json={
                "title": "Provider Failure Meeting",
                "transcript_text": "[00:00:10] Riley Park: The launch date is confirmed as December 10.",
            },
            headers=headers,
        ).json()
        with patch.object(settings, "AI_PROVIDER", "openai"), patch.object(
            settings, "OPENAI_API_KEY", ""
        ):
            result = self.client.post(f"/api/meetings/{meeting['id']}/process", headers=headers)
        self.assertEqual(result.status_code, 502)
        self.assertIn("OPENAI_API_KEY", result.json()["detail"])
        detail = self.client.get(f"/api/meetings/{meeting['id']}", headers=headers)
        self.assertEqual(detail.json()["status"], "FAILED")
        with db.transaction() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM transcript_segments WHERE meeting_id = ?",
                (meeting["id"],),
            ).fetchone()["count"]
        self.assertEqual(count, 0)

    # ------------------------------------------------------------------
    # WORKFLOW C: Central Human Approval Gate & Idempotent Execution
    # ------------------------------------------------------------------
    def test_workflow_c_approval_gate_rejection_execution_and_idempotency(self):
        auth = self._register("test-user-06@example.test", "Liam Brooks", org_name="Gamma Systems")
        headers = self._headers(auth["access_token"])

        # Connect Linear integration
        conn_res = self.client.post(
            "/api/integrations/linear/connect",
            json={"workspace_name": "Gamma Eng", "project_id": "ENG-1"},
            headers=headers,
        )
        self.assertEqual(conn_res.status_code, 200)

        # Create two tasks and prepare external syncs
        t1 = self.client.post("/api/tasks", json={"title": "Ship billing webhook", "priority": "HIGH"}, headers=headers).json()
        t2 = self.client.post("/api/tasks", json={"title": "Draft deprecated spec", "priority": "LOW"}, headers=headers).json()

        a1 = self.client.post(f"/api/tasks/{t1['id']}/prepare-sync", json={"provider": "linear"}, headers=headers).json()
        a2 = self.client.post(f"/api/tasks/{t2['id']}/prepare-sync", json={"provider": "linear"}, headers=headers).json()
        self.assertEqual(a1["status"], "PENDING")

        # Attempt execution WITHOUT approval -> MUST be blocked (403)
        blocked = self.client.post(f"/api/approvals/{a1['id']}/execute", headers=headers)
        self.assertEqual(blocked.status_code, 403)

        # Reject a2 -> execution MUST be blocked
        rej = self.client.post(f"/api/approvals/{a2['id']}/reject", json={"comment": "Out of scope"}, headers=headers)
        self.assertEqual(rej.status_code, 200)
        self.assertEqual(rej.json()["status"], "REJECTED")
        blocked_rej = self.client.post(f"/api/approvals/{a2['id']}/execute", headers=headers)
        self.assertEqual(blocked_rej.status_code, 403)

        # Approve a1 -> Execute -> Verify Linear sync + idempotency on retry
        appr = self.client.post(f"/api/approvals/{a1['id']}/approve", json={"comment": "Approved for sprint"}, headers=headers)
        self.assertEqual(appr.status_code, 200)
        self.assertEqual(appr.json()["status"], "APPROVED")

        exec1 = self.client.post(f"/api/approvals/{a1['id']}/execute", headers=headers)
        self.assertEqual(exec1.status_code, 200, exec1.text)
        exec1_data = exec1.json()
        self.assertEqual(exec1_data["approval"]["status"], "EXECUTED")
        self.assertFalse(exec1_data["execution_record"]["idempotent_replay"])
        ext_ref = exec1_data["execution_record"]["external_reference_id"]
        self.assertTrue(ext_ref.startswith("LIN-"))

        # Retry execution -> MUST return idempotent replay with exact same external_reference_id
        exec2 = self.client.post(f"/api/approvals/{a1['id']}/execute", headers=headers)
        self.assertEqual(exec2.status_code, 200)
        self.assertTrue(exec2.json()["execution_record"]["idempotent_replay"])
        self.assertEqual(exec2.json()["execution_record"]["external_reference_id"], ext_ref)

        # Verify audit logs recorded
        logs = self.client.get("/api/analytics/audit-logs", headers=headers).json()["audit_logs"]
        event_types = {l["event_type"] for l in logs}
        self.assertIn("EXTERNAL_EXECUTION_BLOCKED", event_types)
        self.assertIn("APPROVAL_GRANTED", event_types)
        self.assertIn("EXTERNAL_EXECUTION_SUCCEEDED", event_types)
        self.assertIn("EXTERNAL_EXECUTION_IDEMPOTENT_HIT", event_types)

    # ------------------------------------------------------------------
    # WORKFLOW D: Deadline Reminders & Approval-Gated Dispatch
    # ------------------------------------------------------------------
    def test_workflow_d_reminders_require_approval(self):
        auth = self._register("test-user-07@example.test", "Nora Hayes", org_name="Delta Co")
        headers = self._headers(auth["access_token"])

        task = self.client.post(
            "/api/tasks",
            json={"title": "Submit SOC2 evidence", "deadline": "2026-12-01", "priority": "URGENT"},
            headers=headers,
        ).json()

        rem = self.client.post(
            "/api/reminders/schedule",
            json={"action_item_id": task["id"], "reminder_type": "UPCOMING", "timezone": "Asia/Kolkata"},
            headers=headers,
        )
        self.assertEqual(rem.status_code, 201)
        rem_data = rem.json()
        self.assertEqual(rem_data["status"], "PENDING_APPROVAL")
        approval_id = rem_data["approval_id"]

        # Duplicate schedule prevention
        rem_dup = self.client.post(
            "/api/reminders/schedule",
            json={"action_item_id": task["id"], "reminder_type": "UPCOMING", "timezone": "Asia/Kolkata"},
            headers=headers,
        ).json()
        self.assertEqual(rem_dup["id"], rem_data["id"])

        # Unapproved dispatch blocked
        self.assertEqual(self.client.post(f"/api/approvals/{approval_id}/execute", headers=headers).status_code, 403)

        # Approve and dispatch
        self.client.post(f"/api/approvals/{approval_id}/approve", headers=headers)
        exec_res = self.client.post(f"/api/approvals/{approval_id}/execute", headers=headers)
        self.assertEqual(exec_res.status_code, 200)
        self.assertEqual(exec_res.json()["execution_record"]["provider"], "email")

        # Verify reminder status updated to SENT
        rems = self.client.get("/api/reminders", headers=headers).json()["reminders"]
        self.assertEqual(rems[0]["status"], "SENT")

    # ------------------------------------------------------------------
    # WORKFLOW E: Personalized Weekly Digests Per User
    # ------------------------------------------------------------------
    def test_workflow_e_personalized_weekly_digests(self):
        admin = self._register("test-user-08@example.test", "Priya Nair", org_name="Epsilon AI")
        org_id = admin["organization"]["id"]
        member = self._register("test-user-09@example.test", "Rohan Verma", org_id=org_id, role="MEMBER")
        admin_h = self._headers(admin["access_token"])

        # Assign distinct tasks to Priya (1 completed) and Rohan (1 overdue)
        t_priya = self.client.post(
            "/api/tasks",
            json={"title": "Priya Strategy Review", "assigned_user_id": admin["user"]["id"], "assigned_name": "Priya Nair"},
            headers=admin_h,
        ).json()
        self.client.patch(f"/api/tasks/{t_priya['id']}", json={"status": "COMPLETED"}, headers=admin_h)

        self.client.post(
            "/api/tasks",
            json={
                "title": "Rohan Overdue Migration",
                "assigned_user_id": member["user"]["id"],
                "assigned_name": "Rohan Verma",
                "deadline": "2026-10-01",
                "priority": "HIGH",
            },
            headers=admin_h,
        )

        d_priya = self.client.post(
            "/api/digests/generate",
            json={"user_id": admin["user"]["id"], "delivery_day": "Monday", "timezone": "UTC"},
            headers=admin_h,
        ).json()
        d_rohan = self.client.post(
            "/api/digests/generate",
            json={"user_id": member["user"]["id"], "delivery_day": "Friday", "timezone": "Asia/Kolkata"},
            headers=admin_h,
        ).json()

        # Verify strict personalization
        self.assertEqual(len(d_priya["content"]["completed_tasks"]), 1)
        self.assertEqual(len(d_priya["content"]["overdue_tasks"]), 0)
        self.assertEqual(d_priya["content"]["assigned_tasks"][0]["title"], "Priya Strategy Review")

        self.assertEqual(len(d_rohan["content"]["completed_tasks"]), 0)
        self.assertEqual(len(d_rohan["content"]["overdue_tasks"]), 1)
        self.assertEqual(d_rohan["content"]["assigned_tasks"][0]["title"], "Rohan Overdue Migration")

        # Dispatch blocked until approval
        self.assertEqual(
            self.client.post(f"/api/approvals/{d_priya['approval_id']}/execute", headers=admin_h).status_code,
            403,
        )

        # Approve and dispatch Priya's digest only
        self.client.post(f"/api/approvals/{d_priya['approval_id']}/approve", headers=admin_h)
        res = self.client.post(f"/api/approvals/{d_priya['approval_id']}/execute", headers=admin_h)
        self.assertEqual(res.status_code, 200)

        # Check analytics overview & commitment radar reflect real DB data
        overview = self.client.get("/api/analytics/overview", headers=admin_h).json()
        self.assertEqual(overview["tasks_summary"]["total"], 2)
        self.assertEqual(overview["tasks_summary"]["completed"], 1)
        self.assertEqual(overview["tasks_summary"]["overdue"], 1)

    # ------------------------------------------------------------------
    # WORKFLOW F: Security, RBAC, Cross-Org Isolation & Tamper Protection
    # ------------------------------------------------------------------
    def test_workflow_f_security_isolation_and_approval_invalidation(self):
        # Invalid JWT rejected
        self.assertEqual(
            self.client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.jwt.token"}).status_code,
            401,
        )

        org1_admin = self._register("test-user-10@example.test", "Org1 Boss", org_name="Org One")
        unauthorized_join = self.client.post(
            "/api/auth/register",
            json={
                "email": "test-user-11@example.test",
                "full_name": "Unauthorized Join",
                "password": "StrongPass123!",
                "organization_id": org1_admin["organization"]["id"],
                "role": "ADMIN",
            },
        )
        self.assertEqual(unauthorized_join.status_code, 403)
        unauthorized_role = self.client.post(
            "/api/auth/register",
            json={
                "email": "test-user-12@example.test",
                "full_name": "Unauthorized Role",
                "password": "StrongPass123!",
                "role": "MANAGER",
            },
        )
        self.assertEqual(unauthorized_role.status_code, 403)
        org1_member = self._register(
            "test-user-13@example.test", "Org1 Staff", org_id=org1_admin["organization"]["id"], role="MEMBER"
        )
        org2_admin = self._register("test-user-14@example.test", "Org2 Boss", org_name="Org Two")

        h1_admin = self._headers(org1_admin["access_token"])
        h1_member = self._headers(org1_member["access_token"])
        h2_admin = self._headers(org2_admin["access_token"])

        cross_org_task = self.client.post(
            "/api/tasks",
            json={
                "title": "Cross-organization task",
                "meeting_id": "not-a-meeting",
                "assigned_user_id": org2_admin["user"]["id"],
            },
            headers=h1_admin,
        )
        self.assertEqual(cross_org_task.status_code, 404)
        cross_org_assignee = self.client.post(
            "/api/tasks",
            json={"title": "Foreign assignee task", "assigned_user_id": org2_admin["user"]["id"]},
            headers=h1_admin,
        )
        self.assertEqual(cross_org_assignee.status_code, 404)

        # Invalid file upload rejected
        bad_upload = self.client.post(
            "/api/meetings/upload",
            data={"title": "Malicious Upload"},
            files={"file": ("payload.exe", b"MZ\x90\x00", "application/octet-stream")},
            headers=h1_admin,
        )
        self.assertEqual(bad_upload.status_code, 400)
        with patch.object(settings, "MAX_UPLOAD_SIZE_BYTES", 1):
            oversized_upload = self.client.post(
                "/api/meetings/upload",
                data={"title": "Oversized Upload"},
                files={"file": ("notes.txt", b"too large", "text/plain")},
                headers=h1_admin,
            )
        self.assertEqual(oversized_upload.status_code, 413)

        # Create task & pending approval in Org1
        task = self.client.post("/api/tasks", json={"title": "Org1 Secret Task"}, headers=h1_admin).json()
        approval = self.client.post(f"/api/tasks/{task['id']}/prepare-sync", json={"provider": "trello"}, headers=h1_admin).json()

        # Cross-organization access MUST be blocked (404)
        self.assertEqual(self.client.get(f"/api/approvals/{approval['id']}", headers=h2_admin).status_code, 404)
        self.assertEqual(self.client.post(f"/api/approvals/{approval['id']}/approve", headers=h2_admin).status_code, 404)

        # Unauthorized MEMBER cannot approve (403)
        self.assertEqual(self.client.post(f"/api/approvals/{approval['id']}/approve", headers=h1_member).status_code, 403)

        # Admin approves -> then edits payload -> old approval MUST be invalidated back to PENDING
        self.assertEqual(self.client.post(f"/api/approvals/{approval['id']}/approve", headers=h1_admin).status_code, 200)
        edited = self.client.patch(
            f"/api/approvals/{approval['id']}",
            json={"proposed_content": {"task_id": task["id"], "title": "Tampered Title"}},
            headers=h1_admin,
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()["status"], "PENDING")
        self.assertIsNone(edited.json()["reviewer_id"])
        # Trying to execute after edit MUST be blocked
        self.assertEqual(self.client.post(f"/api/approvals/{approval['id']}/execute", headers=h1_admin).status_code, 403)

        # Simulate direct DB payload tampering after approval -> hash mismatch MUST block execution (409)
        self.assertEqual(self.client.post(f"/api/approvals/{approval['id']}/approve", headers=h1_admin).status_code, 200)
        with db.transaction() as conn:
            conn.execute(
                "UPDATE approvals SET proposed_content_json = ? WHERE id = ?",
                ('{"task_id":"evil","title":"Injected"}', approval["id"]),
            )
        tamper_res = self.client.post(f"/api/approvals/{approval['id']}/execute", headers=h1_admin)
        self.assertEqual(tamper_res.status_code, 409)


if __name__ == "__main__":
    unittest.main(verbosity=2)
