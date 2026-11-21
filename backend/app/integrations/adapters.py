import hashlib
import smtplib
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from typing import Any, Dict, Optional
from urllib.parse import quote

import httpx

from app.core.config import settings


def _mock_mode() -> bool:
    if settings.INTEGRATION_MODE not in {"mock", "live"}:
        raise RuntimeError("INTEGRATION_MODE must be 'mock' or 'live'.")
    return settings.INTEGRATION_MODE == "mock"


def _http_json(method: str, url: str, provider: str, **kwargs: Any) -> Any:
    try:
        response = httpx.request(method, url, timeout=20.0, **kwargs)
    except httpx.RequestError as exc:
        raise RuntimeError(f"{provider} request could not be completed.") from exc
    if not response.is_success:
        raise RuntimeError(f"{provider} returned HTTP {response.status_code}.")
    if not response.content:
        return {}
    try:
        value = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{provider} returned an invalid response.") from exc
    return value


def validate_integration_configuration(
    provider: str, config: Optional[Dict[str, Any]] = None
) -> None:
    if _mock_mode():
        return
    config = config or {}
    configured = {
        "linear": bool(settings.LINEAR_API_KEY and (config.get("team_id") or settings.LINEAR_TEAM_ID)),
        "trello": bool(
            settings.TRELLO_API_KEY
            and settings.TRELLO_TOKEN
        and (config.get("list_id") or config.get("project_id") or settings.TRELLO_LIST_ID)
        ),
        "email": bool(settings.SMTP_HOST and settings.SMTP_FROM_EMAIL),
        "google_calendar": bool(settings.GOOGLE_CALENDAR_ACCESS_TOKEN),
        "slack": False,
    }
    if not configured.get(provider, False):
        raise ValueError(f"{provider} is missing required live provider environment settings.")


def _mapped_assignee_id(payload: Dict[str, Any], connection_config: Dict[str, Any]) -> Optional[str]:
    user_id = payload.get("assigned_user_id")
    if not user_id:
        return None
    user_id_map = connection_config.get("user_id_map", {})
    provider_user_id = user_id_map.get(str(user_id)) if isinstance(user_id_map, dict) else None
    if not provider_user_id:
        raise RuntimeError("Map the MeetFlow assignee to a provider user ID in the integration configuration.")
    return str(provider_user_id)


class BaseIntegrationAdapter(ABC):
    provider_name: str = "base"

    @abstractmethod
    def execute(
        self,
        action_type: str,
        payload: Dict[str, Any],
        idempotency_key: str,
        connection_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute an authorized external action idempotently."""


class LinearAdapter(BaseIntegrationAdapter):
    provider_name = "linear"

    def execute(
        self,
        action_type: str,
        payload: Dict[str, Any],
        idempotency_key: str,
        connection_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not _mock_mode():
            return self._execute_live(action_type, payload, idempotency_key, connection_config)
        # Deterministic external issue identifier bound to idempotency key
        short_num = int(hashlib.sha256(idempotency_key.encode()).hexdigest()[:6], 16) % 9000 + 100
        ext_id = f"LIN-{short_num}"
        return {
            "provider": "linear",
            "simulated": True,
            "action_type": action_type,
            "external_reference_id": ext_id,
            "workspace": connection_config.get("workspace_name", "MeetFlow Workspace"),
            "project_id": connection_config.get("project_id", "default-team"),
            "synced_title": payload.get("title"),
            "assignee": payload.get("assigned_name"),
            "due_date": payload.get("deadline"),
            "priority": payload.get("priority", "MEDIUM"),
            "status": "CREATED" if action_type == "EXTERNAL_TASK_CREATE" else "UPDATED",
        }

    def _execute_live(self, action_type, payload, idempotency_key, connection_config):
        if not settings.LINEAR_API_KEY:
            raise RuntimeError("LINEAR_API_KEY is not configured.")
        team_id = connection_config.get("team_id") or settings.LINEAR_TEAM_ID
        if not team_id:
            raise RuntimeError("LINEAR_TEAM_ID is not configured.")
        input_data = {
            "teamId": team_id,
            "title": payload.get("title"),
            "description": payload.get("description") or "",
            "clientMutationId": idempotency_key,
        }
        assignee_id = _mapped_assignee_id(payload, connection_config)
        if assignee_id:
            input_data["assigneeId"] = assignee_id
        if payload.get("deadline"):
            input_data["dueDate"] = str(payload["deadline"])[:10]
        priority = payload.get("priority")
        priority_map = {"URGENT": 1, "HIGH": 2, "MEDIUM": 3, "LOW": 4}
        if priority in priority_map:
            input_data["priority"] = priority_map[priority]
        elif priority in {1, 2, 3, 4}:
            input_data["priority"] = priority
        if action_type == "EXTERNAL_TASK_UPDATE":
            issue_id = payload.get("external_task_id")
            if not issue_id:
                raise RuntimeError("Linear issue ID is required for task updates.")
            operation = "issueUpdate"
            input_data.pop("teamId", None)
            input_data["id"] = issue_id
        else:
            operation = "issueCreate"
        query = (
            f"mutation MeetFlow($input: {'IssueUpdateInput' if operation == 'issueUpdate' else 'IssueCreateInput'}!) "
            f"{{ {operation}(input: $input) {{ success issue {{ id identifier url }} }} }}"
        )
        body = _http_json(
            "POST",
            "https://api.linear.app/graphql",
            "Linear",
            headers={"Authorization": settings.LINEAR_API_KEY, "Content-Type": "application/json"},
            json={"query": query, "variables": {"input": input_data}},
        )
        result = body.get("data", {}).get(operation, {})
        issue = result.get("issue") or {}
        if not result.get("success") or not issue.get("id"):
            raise RuntimeError("Linear did not confirm the requested issue operation.")
        return {
            "provider": "linear",
            "simulated": False,
            "action_type": action_type,
            "external_reference_id": issue["id"],
            "identifier": issue.get("identifier"),
            "url": issue.get("url"),
            "status": "CREATED" if action_type == "EXTERNAL_TASK_CREATE" else "UPDATED",
        }


class TrelloAdapter(BaseIntegrationAdapter):
    provider_name = "trello"

    def execute(
        self,
        action_type: str,
        payload: Dict[str, Any],
        idempotency_key: str,
        connection_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not _mock_mode():
            return self._execute_live(action_type, payload, idempotency_key, connection_config)
        card_id = f"tr_{hashlib.sha256(idempotency_key.encode()).hexdigest()[:10]}"
        return {
            "provider": "trello",
            "simulated": True,
            "action_type": action_type,
            "external_reference_id": card_id,
            "board": connection_config.get("workspace_name", "MeetFlow Board"),
            "card_name": payload.get("title"),
            "due": payload.get("deadline"),
            "status": "CARD_SYNCED",
        }

    def _execute_live(self, action_type, payload, idempotency_key, connection_config):
        if not settings.TRELLO_API_KEY or not settings.TRELLO_TOKEN:
            raise RuntimeError("TRELLO_API_KEY and TRELLO_TOKEN are required.")
        list_id = (
            connection_config.get("list_id")
            or connection_config.get("project_id")
            or settings.TRELLO_LIST_ID
        )
        if not list_id:
            raise RuntimeError("Select a Trello list by setting the integration list_id.")
        base = "https://api.trello.com/1"
        auth_params = {"key": settings.TRELLO_API_KEY, "token": settings.TRELLO_TOKEN}
        marker = f"MeetFlow idempotency key: {idempotency_key}"
        if action_type == "EXTERNAL_TASK_UPDATE":
            card_id = payload.get("external_task_id")
            if not card_id:
                raise RuntimeError("Trello card ID is required for task updates.")
            fields = {"name": payload.get("title", ""), "desc": f"{payload.get('description') or ''}\n\n{marker}"}
            if payload.get("deadline"):
                fields["due"] = str(payload["deadline"])
            card = _http_json(
                "PUT", f"{base}/cards/{card_id}", "Trello",
                params=auth_params, data=fields,
            )
        else:
            cards = _http_json(
                "GET", f"{base}/lists/{list_id}/cards", "Trello",
                params={**auth_params, "fields": "id,name,desc"},
            )
            if isinstance(cards, list):
                existing = next(
                    (card for card in cards if marker in str(card.get("desc", ""))), None
                )
                if existing:
                    return {
                        "provider": "trello", "simulated": False, "action_type": action_type,
                        "external_reference_id": existing["id"], "status": "CARD_EXISTS",
                    }
            card_fields = {
                "idList": list_id,
                "name": payload.get("title", ""),
                "desc": f"{payload.get('description') or ''}\n\n{marker}",
            }
            if payload.get("deadline"):
                card_fields["due"] = str(payload["deadline"])
            assignee_id = _mapped_assignee_id(payload, connection_config)
            if assignee_id:
                card_fields["idMembers"] = assignee_id
            card = _http_json(
                "POST", f"{base}/cards", "Trello", params=auth_params, data=card_fields,
            )
        if not card.get("id"):
            raise RuntimeError("Trello did not return a card ID.")
        return {
            "provider": "trello", "simulated": False, "action_type": action_type,
            "external_reference_id": card["id"], "status": "CARD_SYNCED",
        }


class EmailAdapter(BaseIntegrationAdapter):
    provider_name = "email"

    def execute(
        self,
        action_type: str,
        payload: Dict[str, Any],
        idempotency_key: str,
        connection_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not _mock_mode():
            return self._execute_live(action_type, payload, idempotency_key)
        msg_id = f"msg_{hashlib.sha256(idempotency_key.encode()).hexdigest()[:12]}"
        return {
            "provider": "email",
            "simulated": True,
            "action_type": action_type,
            "external_reference_id": msg_id,
            "recipient": payload.get("recipient_email") or payload.get("assigned_name") or "team@organization",
            "subject": payload.get("subject") or f"MeetFlow Notification: {action_type}",
            "status": "DISPATCHED",
        }

    def _execute_live(self, action_type, payload, idempotency_key):
        if not settings.SMTP_HOST or not settings.SMTP_FROM_EMAIL:
            raise RuntimeError("SMTP_HOST and SMTP_FROM_EMAIL are required.")
        recipient = payload.get("recipient_email")
        if not recipient or "@" not in recipient:
            raise RuntimeError("A valid recipient_email is required for email delivery.")
        message = EmailMessage()
        message["From"] = settings.SMTP_FROM_EMAIL
        message["To"] = recipient
        message["Subject"] = payload.get("subject") or f"MeetFlow: {action_type}"
        message["Message-ID"] = (
            f"<meetflow-{hashlib.sha256(idempotency_key.encode()).hexdigest()}@meetflow.local>"
        )
        message.set_content(payload.get("body") or payload.get("message") or payload.get("content") or "")
        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as client:
                if settings.SMTP_USE_TLS:
                    client.starttls()
                if settings.SMTP_USERNAME:
                    client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                refused = client.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise RuntimeError("SMTP delivery failed.") from exc
        if refused:
            raise RuntimeError("SMTP server refused the recipient.")
        return {
            "provider": "email", "simulated": False, "action_type": action_type,
            "external_reference_id": message["Message-ID"],
            "recipient": recipient, "status": "DISPATCHED",
        }


class GoogleCalendarAdapter(BaseIntegrationAdapter):
    provider_name = "google_calendar"

    def execute(
        self,
        action_type: str,
        payload: Dict[str, Any],
        idempotency_key: str,
        connection_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not _mock_mode():
            return self._execute_live(action_type, payload, idempotency_key, connection_config)
        event_id = f"gcal_{hashlib.sha256(idempotency_key.encode()).hexdigest()[:10]}"
        return {
            "provider": "google_calendar",
            "simulated": True,
            "action_type": action_type,
            "external_reference_id": event_id,
            "status": "EVENT_UPDATED",
        }

    def _execute_live(self, action_type, payload, idempotency_key, connection_config):
        token = settings.GOOGLE_CALENDAR_ACCESS_TOKEN
        if not token:
            raise RuntimeError("GOOGLE_CALENDAR_ACCESS_TOKEN is not configured.")
        calendar_id = connection_config.get("calendar_id") or settings.GOOGLE_CALENDAR_ID
        event_id = hashlib.sha256(idempotency_key.encode()).hexdigest()
        base = f"{settings.GOOGLE_CALENDAR_API_URL}/calendars/{quote(str(calendar_id), safe='')}/events"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        start = payload.get("start") or payload.get("deadline")
        end = payload.get("end")
        if not start:
            raise RuntimeError("A start date/time is required to create a calendar event.")
        if isinstance(start, str) and len(start) == 10:
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end) if isinstance(end, str) and len(end) == 10 else start_date + timedelta(days=1)
            start_value, end_value = {"date": start_date.isoformat()}, {"date": end_date.isoformat()}
        else:
            start_value = {"dateTime": start}
            end_value = {"dateTime": end or (datetime.fromisoformat(start.replace("Z", "+00:00")) + timedelta(hours=1)).isoformat()}
        event_body = {
            "id": event_id,
            "summary": payload.get("title") or payload.get("summary") or "MeetFlow event",
            "description": payload.get("description") or payload.get("body") or "",
            "start": start_value,
            "end": end_value,
        }
        if action_type == "CALENDAR_UPDATE" and payload.get("external_event_id"):
            event = _http_json(
                "PUT", f"{base}/{payload['external_event_id']}", "Google Calendar",
                headers=headers, json=event_body,
            )
        else:
            existing = httpx.get(f"{base}/{event_id}", headers=headers, timeout=20.0)
            if existing.status_code == 200:
                event = existing.json()
            elif existing.status_code == 404:
                event = _http_json("POST", base, "Google Calendar", headers=headers, json=event_body)
            else:
                raise RuntimeError(f"Google Calendar returned HTTP {existing.status_code}.")
        if not event.get("id"):
            raise RuntimeError("Google Calendar did not return an event ID.")
        return {
            "provider": "google_calendar", "simulated": False, "action_type": action_type,
            "external_reference_id": event["id"], "status": "EVENT_CREATED",
        }


class NotificationAdapter(BaseIntegrationAdapter):
    provider_name = "slack"

    def execute(
        self,
        action_type: str,
        payload: Dict[str, Any],
        idempotency_key: str,
        connection_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not _mock_mode():
            raise RuntimeError("Slack live delivery is not configured; use INTEGRATION_MODE=mock.")
        notif_id = f"slk_{hashlib.sha256(idempotency_key.encode()).hexdigest()[:10]}"
        return {
            "provider": "slack",
            "simulated": True,
            "action_type": action_type,
            "external_reference_id": notif_id,
            "status": "POSTED",
        }


ADAPTER_REGISTRY: Dict[str, BaseIntegrationAdapter] = {
    "linear": LinearAdapter(),
    "trello": TrelloAdapter(),
    "email": EmailAdapter(),
    "google_calendar": GoogleCalendarAdapter(),
    "slack": NotificationAdapter(),
}


def get_adapter(provider: str) -> BaseIntegrationAdapter:
    adapter = ADAPTER_REGISTRY.get(provider.lower())
    if not adapter:
        raise ValueError(f"Unsupported integration provider: '{provider}'")
    return adapter
