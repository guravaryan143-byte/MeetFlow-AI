import hashlib
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.integrations.adapters import (
    EmailAdapter,
    GoogleCalendarAdapter,
    LinearAdapter,
    TrelloAdapter,
    validate_integration_configuration,
)


class IntegrationAdapterTests(unittest.TestCase):
    def test_linear_live_create_uses_auth_and_provider_idempotency(self):
        body = {
            "data": {
                "issueCreate": {
                    "success": True,
                    "issue": {"id": "issue-1", "identifier": "MF-1", "url": "https://linear.test/MF-1"},
                }
            }
        }
        with patch.object(settings, "INTEGRATION_MODE", "live"), patch.object(
            settings, "LINEAR_API_KEY", "mock-linear-key"
        ), patch("app.integrations.adapters._http_json", return_value=body) as request:
            result = LinearAdapter().execute(
                "EXTERNAL_TASK_CREATE",
                {"title": "Review launch", "assigned_user_id": "user-1", "priority": "HIGH"},
                "stable-idempotency-key",
                {"team_id": "team-1", "user_id_map": {"user-1": "linear-user-1"}},
            )
        self.assertFalse(result["simulated"])
        self.assertEqual(result["external_reference_id"], "issue-1")
        query_body = request.call_args.kwargs["json"]
        self.assertEqual(query_body["variables"]["input"]["clientMutationId"], "stable-idempotency-key")
        self.assertEqual(query_body["variables"]["input"]["assigneeId"], "linear-user-1")
        self.assertEqual(query_body["variables"]["input"]["priority"], 2)

    def test_linear_live_assignment_requires_provider_user_mapping(self):
        with patch.object(settings, "INTEGRATION_MODE", "live"), patch.object(
            settings, "LINEAR_API_KEY", "mock-linear-key"
        ):
            with self.assertRaisesRegex(RuntimeError, "Map the MeetFlow assignee"):
                LinearAdapter().execute(
                    "EXTERNAL_TASK_CREATE",
                    {"title": "Review launch", "assigned_user_id": "meetflow-user-1"},
                    "stable-idempotency-key",
                    {"team_id": "team-1"},
                )

    def test_trello_live_create_checks_existing_idempotency_marker(self):
        with patch.object(settings, "INTEGRATION_MODE", "live"), patch.object(
            settings, "TRELLO_API_KEY", "key"
        ), patch.object(settings, "TRELLO_TOKEN", "token"), patch(
            "app.integrations.adapters._http_json",
            side_effect=[[], {"id": "card-1", "name": "Review launch"}],
        ) as request:
            result = TrelloAdapter().execute(
                "EXTERNAL_TASK_CREATE",
                {"title": "Review launch"},
                "stable-key",
                {"list_id": "list-1"},
            )
        self.assertFalse(result["simulated"])
        self.assertEqual(result["external_reference_id"], "card-1")
        self.assertEqual(request.call_count, 2)
        self.assertIn("stable-key", request.call_args.kwargs["data"]["desc"])

    def test_trello_returns_prior_card_for_same_idempotency_key(self):
        existing = [{"id": "card-existing", "desc": "MeetFlow idempotency key: stable-key"}]
        with patch.object(settings, "INTEGRATION_MODE", "live"), patch.object(
            settings, "TRELLO_API_KEY", "key"
        ), patch.object(settings, "TRELLO_TOKEN", "token"), patch(
            "app.integrations.adapters._http_json", return_value=existing
        ) as request:
            result = TrelloAdapter().execute(
                "EXTERNAL_TASK_CREATE", {"title": "Review"}, "stable-key", {"list_id": "list-1"}
            )
        self.assertEqual(result["external_reference_id"], "card-existing")
        self.assertEqual(request.call_count, 1)

    def test_smtp_live_delivery_is_mocked_and_uses_stable_message_id(self):
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp
        smtp.send_message.return_value = {}
        with patch.object(settings, "INTEGRATION_MODE", "live"), patch.object(
            settings, "SMTP_HOST", "smtp.test"
        ), patch.object(settings, "SMTP_FROM_EMAIL", "meetflow@example.test"), patch.object(
            settings, "SMTP_USE_TLS", False
        ), patch("app.integrations.adapters.smtplib.SMTP", return_value=smtp):
            result = EmailAdapter().execute(
                "EMAIL_DISPATCH",
                {"recipient_email": "recipient@example.test", "body": "Approved reminder"},
                "stable-key",
                {},
            )
        self.assertFalse(result["simulated"])
        self.assertEqual(result["recipient"], "recipient@example.test")
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["To"], "recipient@example.test")
        expected_id = hashlib.sha256(b"stable-key").hexdigest()
        self.assertEqual(message["Message-ID"], f"<meetflow-{expected_id}@meetflow.local>")
        self.assertEqual(message["Message-ID"], result["external_reference_id"])

    def test_calendar_live_create_uses_deterministic_event_id(self):
        missing = MagicMock(status_code=404)

        def create_event(*args, **kwargs):
            return {"id": kwargs["json"]["id"]}

        with patch.object(settings, "INTEGRATION_MODE", "live"), patch.object(
            settings, "GOOGLE_CALENDAR_ACCESS_TOKEN", "mock-google-token"
        ), patch("app.integrations.adapters.httpx.get", return_value=missing), patch(
            "app.integrations.adapters._http_json", side_effect=create_event
        ) as request:
            first = GoogleCalendarAdapter().execute(
                "CALENDAR_UPDATE",
                {"title": "Launch", "start": "2026-12-10"},
                "stable-calendar-key",
                {},
            )
        self.assertFalse(first["simulated"])
        event = request.call_args.kwargs["json"]
        self.assertEqual(event["id"], first["external_reference_id"])
        self.assertEqual(event["start"]["date"], "2026-12-10")

    def test_live_configuration_requires_backend_credentials(self):
        with patch.object(settings, "INTEGRATION_MODE", "live"), patch.object(
            settings, "LINEAR_API_KEY", ""
        ):
            with self.assertRaisesRegex(ValueError, "missing required"):
                validate_integration_configuration("linear", {"team_id": "team"})


if __name__ == "__main__":
    unittest.main()
