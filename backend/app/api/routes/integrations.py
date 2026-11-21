import json
import sqlite3
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.approvals.execution_service import AUTHORIZED_APPROVER_ROLES
from app.core.config import settings
from app.db.database import get_db, new_uuid, record_audit_log, utc_now
from app.integrations.adapters import validate_integration_configuration
from app.schemas.schemas import IntegrationConnectRequest

router = APIRouter(prefix="/api/integrations", tags=["Integrations"])
SUPPORTED_PROVIDERS = {"linear", "trello", "google_calendar", "email", "slack"}


@router.get("")
def list_integrations(
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = conn.execute(
        "SELECT id, organization_id, provider, workspace_name, project_id, status, created_at, updated_at FROM integration_connections WHERE organization_id = ?",
        (current_user["organization_id"],),
    ).fetchall()
    return {
        "integrations": [dict(r) for r in rows],
        "mode": settings.INTEGRATION_MODE,
        "simulated": settings.INTEGRATION_MODE == "mock",
    }


@router.post("/{provider}/connect")
def connect_integration(
    provider: str,
    payload: IntegrationConnectRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    provider_key = provider.lower()
    if provider_key not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider '{provider}'.")
    if current_user["role"] not in AUTHORIZED_APPROVER_ROLES:
        raise HTTPException(status_code=403, detail="Only ADMIN or MANAGER roles can connect integrations.")
    if payload.api_token:
        raise HTTPException(
            status_code=400,
            detail="Provider credentials are not stored through this API. Configure them as backend environment variables.",
        )
    try:
        validate_integration_configuration(provider_key, payload.config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    now = utc_now()
    safe_config = {k: v for k, v in payload.config.items() if "secret" not in k.lower() and "token" not in k.lower()}
    if provider_key == "linear":
        safe_config.setdefault("team_id", settings.LINEAR_TEAM_ID)
    elif provider_key == "trello":
        safe_config.setdefault("list_id", settings.TRELLO_LIST_ID)
    elif provider_key == "google_calendar":
        safe_config.setdefault("calendar_id", settings.GOOGLE_CALENDAR_ID)

    existing = conn.execute(
        "SELECT id FROM integration_connections WHERE organization_id = ? AND provider = ?",
        (current_user["organization_id"], provider_key),
    ).fetchone()

    if existing:
        conn_id = existing["id"]
        conn.execute(
            """
            UPDATE integration_connections
            SET workspace_name = ?, project_id = ?, config_json = ?, status = 'CONNECTED', updated_at = ?
            WHERE id = ?
            """,
            (payload.workspace_name, payload.project_id, json.dumps(safe_config), now, conn_id),
        )
    else:
        conn_id = new_uuid()
        conn.execute(
            """
            INSERT INTO integration_connections (
                id, organization_id, provider, workspace_name, project_id,
                config_json, status, connected_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'CONNECTED', ?, ?, ?)
            """,
            (
                conn_id,
                current_user["organization_id"],
                provider_key,
                payload.workspace_name,
                payload.project_id,
                json.dumps(safe_config),
                current_user["user_id"],
                now,
                now,
            ),
        )

    record_audit_log(
        conn,
        current_user["organization_id"],
        current_user["user_id"],
        "INTEGRATION_CONNECTED",
        "integration_connection",
        conn_id,
        {"provider": provider_key, "workspace_name": payload.workspace_name},
    )

    return {
        "id": conn_id,
        "provider": provider_key,
        "workspace_name": payload.workspace_name,
        "project_id": payload.project_id,
        "status": "CONNECTED",
        "mode": settings.INTEGRATION_MODE,
    }
