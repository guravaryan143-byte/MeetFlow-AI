import sqlite3
from typing import Any, Dict

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_access_token
from app.db.database import get_db

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    conn: sqlite3.Connection = Depends(get_db),
) -> Dict[str, Any]:
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
        )

    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired JWT token.",
        )

    user_row = conn.execute(
        "SELECT id, email, full_name, timezone, is_active FROM users WHERE id = ?",
        (payload["sub"],),
    ).fetchone()
    if not user_row or not user_row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive or does not exist.",
        )

    membership = conn.execute(
        """
        SELECT om.organization_id, om.role, o.name AS organization_name, o.slug AS organization_slug
        FROM organization_memberships om
        JOIN organizations o ON o.id = om.organization_id
        WHERE om.user_id = ? AND om.organization_id = ?
        """,
        (user_row["id"], payload["org_id"]),
    ).fetchone()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization membership is not valid.",
        )

    return {
        "user_id": user_row["id"],
        "email": user_row["email"],
        "full_name": user_row["full_name"],
        "timezone": user_row["timezone"],
        "organization_id": membership["organization_id"],
        "organization_name": membership["organization_name"],
        "organization_slug": membership["organization_slug"],
        "role": membership["role"],
    }
