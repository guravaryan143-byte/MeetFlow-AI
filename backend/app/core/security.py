import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, Optional

from app.core.config import settings


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 and a random 16-byte salt."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260_000)
    return f"pbkdf2_sha256$260000${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plaintext password against a stored PBKDF2-HMAC-SHA256 hash."""
    try:
        scheme, iterations_str, salt_b64, dk_b64 = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iterations_str)
        salt = base64.b64decode(salt_b64)
        expected_dk = base64.b64decode(dk_b64)
        actual_dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual_dk, expected_dk)
    except Exception:
        return False


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def create_access_token(
    user_id: str,
    email: str,
    org_id: str,
    role: str,
    expires_minutes: Optional[int] = None,
) -> str:
    """Create a standards-compliant HS256 JWT token."""
    now = int(time.time())
    exp = now + (expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES) * 60
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "email": email,
        "org_id": org_id,
        "role": role,
        "iat": now,
        "exp": exp,
    }
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(
        settings.JWT_SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and verify an HS256 JWT token. Returns None if invalid or expired."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected_sig = hmac.new(
            settings.JWT_SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256
        ).digest()
        actual_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
        if header.get("alg") != "HS256":
            return None
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def compute_payload_hash(payload: Dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash of an approval payload for tamper detection."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generate_idempotency_key(org_id: str, action_type: str, target_provider: str, payload: Dict[str, Any]) -> str:
    """Generate a deterministic idempotency key to prevent duplicate external executions."""
    raw = f"{org_id}:{action_type}:{target_provider}:{compute_payload_hash(payload)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
