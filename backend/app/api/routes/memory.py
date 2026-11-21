import json
import sqlite3
from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.agents.memory import CrossMeetingMemoryAgent
from app.api.deps import get_current_user
from app.db.database import get_db
from app.schemas.schemas import MemorySearchRequest

router = APIRouter(prefix="/api/memory", tags=["Cross-Meeting Memory"])
memory_agent = CrossMeetingMemoryAgent()


@router.post("/search")
def search_memory(
    payload: MemorySearchRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    results = memory_agent.search_decisions(
        conn=conn,
        organization_id=current_user["organization_id"],
        query=payload.query,
        top_k=payload.top_k,
        status_filter=payload.status_filter,
    )
    cleaned = []
    for r in results:
        r["participants"] = json.loads(r.pop("participants_json") or "[]")
        r.pop("embedding_json", None)
        cleaned.append(r)
    return {"query": payload.query, "results": cleaned}


@router.get("/history")
def get_memory_history(
    current_user: Dict[str, Any] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    versions = [
        dict(r)
        for r in conn.execute(
            """
            SELECT dv.*, d.subject, m.title AS meeting_title
            FROM decision_versions dv
            JOIN decisions d ON dv.decision_id = d.id
            JOIN meetings m ON dv.source_meeting_id = m.id
            WHERE dv.organization_id = ?
            ORDER BY dv.created_at DESC
            """,
            (current_user["organization_id"],),
        ).fetchall()
    ]
    return {"history": versions}
