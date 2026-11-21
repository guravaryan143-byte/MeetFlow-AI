import re
import sqlite3
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.database import get_db, new_uuid, record_audit_log, utc_now
from app.schemas.schemas import AuthResponse, LoginRequest, RegisterRequest

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "org"
    return f"{base}-{new_uuid()[:6]}"


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, conn: sqlite3.Connection = Depends(get_db)):
    if payload.organization_id:
        raise HTTPException(
            status_code=403,
            detail="Joining an existing workspace requires an invitation; self-service workspace joining is disabled.",
        )
    if payload.role != "ADMIN":
        raise HTTPException(
            status_code=403,
            detail="Workspace roles are assigned by an existing workspace administrator.",
        )

    existing = conn.execute("SELECT id FROM users WHERE email = ?", (payload.email,)).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    now = utc_now()
    user_id = new_uuid()
    conn.execute(
        """
        INSERT INTO users (id, email, full_name, password_hash, timezone, is_active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (
            user_id,
            payload.email,
            payload.full_name,
            hash_password(payload.password),
            payload.timezone,
            now,
            now,
        ),
    )

    org_id = new_uuid()
    org_name = payload.organization_name or f"{payload.full_name}'s Workspace"
    org_slug = _slugify(org_name)
    role = "ADMIN"
    conn.execute(
        """
        INSERT INTO organizations (id, name, slug, settings_json, created_at, updated_at)
        VALUES (?, ?, ?, '{}', ?, ?)
        """,
        (org_id, org_name, org_slug, now, now),
    )

    conn.execute(
        """
        INSERT INTO organization_memberships (id, organization_id, user_id, role, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (new_uuid(), org_id, user_id, role, now),
    )

    record_audit_log(
        conn, org_id, user_id, "USER_REGISTERED", "user", user_id, {"role": role}
    )

    token = create_access_token(user_id=user_id, email=payload.email, org_id=org_id, role=role)
    return AuthResponse(
        access_token=token,
        user={"id": user_id, "email": payload.email, "full_name": payload.full_name, "timezone": payload.timezone},
        organization={"id": org_id, "name": org_name, "slug": org_slug},
        role=role,
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, conn: sqlite3.Connection = Depends(get_db)):
    email = payload.email.strip().lower()
    user_row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user_row or not verify_password(payload.password, user_row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    membership = conn.execute(
        """
        SELECT om.organization_id, om.role, o.name AS org_name, o.slug AS org_slug
        FROM organization_memberships om
        JOIN organizations o ON o.id = om.organization_id
        WHERE om.user_id = ?
        ORDER BY om.created_at ASC LIMIT 1
        """,
        (user_row["id"],),
    ).fetchone()
    if not membership:
        raise HTTPException(status_code=403, detail="User has no active organization membership.")

    token = create_access_token(
        user_id=user_row["id"],
        email=user_row["email"],
        org_id=membership["organization_id"],
        role=membership["role"],
    )
    return AuthResponse(
        access_token=token,
        user={
            "id": user_row["id"],
            "email": user_row["email"],
            "full_name": user_row["full_name"],
            "timezone": user_row["timezone"],
        },
        organization={
            "id": membership["organization_id"],
            "name": membership["org_name"],
            "slug": membership["org_slug"],
        },
        role=membership["role"],
    )


@router.get("/me")
def me(current_user: Dict[str, Any] = Depends(get_current_user)):
    return current_user
