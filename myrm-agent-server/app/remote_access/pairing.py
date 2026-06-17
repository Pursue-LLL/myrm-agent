"""Signed short-lived tokens for mobile deep links and session discovery."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path

from app.config.settings import settings

PAIRING_TOKEN_TTL_SECONDS = 60 * 60
_KEY_FILE = Path("webui") / "pairing_key"


def _pairing_key_path() -> Path:
    return Path(settings.database.state_dir) / _KEY_FILE


def _load_or_create_key() -> bytes:
    path = _pairing_key_path()
    if path.is_file():
        raw = path.read_bytes()
        if len(raw) >= 32:
            return raw[:32]
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    path.write_bytes(key)
    path.chmod(0o600)
    return key


def _sign(payload: str) -> str:
    digest = hmac.new(_load_or_create_key(), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def create_pairing_token(*, chat_id: str | None = None, purpose: str = "mobile_hub") -> str:
    expires_at = int(time.time()) + PAIRING_TOKEN_TTL_SECONDS
    body = json.dumps(
        {"chat_id": chat_id, "purpose": purpose, "exp": expires_at},
        separators=(",", ":"),
    )
    body_b64 = base64.urlsafe_b64encode(body.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{body_b64}.{_sign(body_b64)}"


def parse_pairing_token(token: str | None) -> dict[str, object] | None:
    if not token or "." not in token:
        return None
    body_b64, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(_sign(body_b64), signature):
        return None
    try:
        padded = body_b64 + "=" * (-len(body_b64) % 4)
        body = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (json.JSONDecodeError, ValueError, binascii.Error):
        return None
    if not isinstance(body, dict):
        return None
    expires_at = body.get("exp")
    if not isinstance(expires_at, int) or expires_at < int(time.time()):
        return None
    chat_id = body.get("chat_id")
    purpose = body.get("purpose")
    if chat_id is not None and not isinstance(chat_id, str):
        return None
    if not isinstance(purpose, str):
        return None
    return {"chat_id": chat_id, "purpose": purpose, "exp": expires_at}


__all__ = [
    "PAIRING_TOKEN_TTL_SECONDS",
    "create_pairing_token",
    "parse_pairing_token",
]
