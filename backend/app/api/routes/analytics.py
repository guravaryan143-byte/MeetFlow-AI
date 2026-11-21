import json
import sqlite3
from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.agents.reporting import ReportingAgent
from app.api.deps import get_current_user
from app.db.database import get_db

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])
reporting_agent = ReportingAgent()


@router.get("/overview")
def analytics_overview(
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    return reporting_agent.compute_analytics_overview(conn, current_user["organization_id"])


@router.get("/radar")
def commitment_radar(
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    return reporting_agent.compute_commitment_radar(conn, current_user["organization_id"])


@router.get("/audit-logs")
def list_audit_logs(
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = conn.execute(
        """
        SELECT * FROM audit_logs
        WHERE organization_id = ?
        ORDER BY created_at DESC LIMIT 200
        """,
        (current_user["organization_id"],),
    ).fetchall()
    logs = []
    for r in rows:
        item = dict(r)
        item["details"] = json.loads(item.pop("details_json") or "{}")
        logs.append(item)
    return {"audit_logs": logs}
