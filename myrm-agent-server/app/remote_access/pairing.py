"""Signed short-lived tokens for mobile deep links and session discovery.

[POS]
HMAC-signed pairing tokens with TTL for mobile remote access deep links.
"""

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
PAIRING_REFRESH_GRACE_SECONDS = 300
MOBILE_HUB_LIST_PURPOSE = "mobile_hub_list"
MOBILE_HUB_CONTROL_PURPOSE = "mobile_hub"
BROWSER_TAKEOVER_PURPOSE = "browser_takeover"
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


def create_pairing_token(
    *,
    chat_id: str | None = None,
    purpose: str = MOBILE_HUB_LIST_PURPOSE,
) -> str:
    issued_at = int(time.time())
    expires_at = issued_at + PAIRING_TOKEN_TTL_SECONDS
    body = json.dumps(
        {
            "chat_id": chat_id,
            "purpose": purpose,
            "exp": expires_at,
            "iat": issued_at,
            "jti": secrets.token_hex(8),
        },
        separators=(",", ":"),
    )
    body_b64 = base64.urlsafe_b64encode(body.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{body_b64}.{_sign(body_b64)}"


def _decode_pairing_body(token: str | None) -> dict[str, object] | None:
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
    chat_id = body.get("chat_id")
    purpose = body.get("purpose")
    if not isinstance(expires_at, int):
        return None
    if chat_id is not None and not isinstance(chat_id, str):
        return None
    if not isinstance(purpose, str):
        return None
    return {"chat_id": chat_id, "purpose": purpose, "exp": expires_at}


def parse_pairing_token(token: str | None) -> dict[str, object] | None:
    body = _decode_pairing_body(token)
    if body is None:
        return None
    if body["exp"] < int(time.time()):
        return None
    return body


def rotate_pairing_key() -> None:
    """Regenerate the HMAC signing key, invalidating all outstanding pair tokens."""
    path = _pairing_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    path.write_bytes(key)
    path.chmod(0o600)


def refresh_pairing_token(
    token: str | None,
    *,
    grace_seconds: int = PAIRING_REFRESH_GRACE_SECONDS,
) -> str | None:
    body = _decode_pairing_body(token)
    if body is None:
        return None
    if body["exp"] + grace_seconds < int(time.time()):
        return None
    chat_id = body.get("chat_id")
    purpose = body["purpose"]
    return create_pairing_token(
        chat_id=chat_id if isinstance(chat_id, str) else None,
        purpose=purpose,
    )


__all__ = [
    "BROWSER_TAKEOVER_PURPOSE",
    "MOBILE_HUB_CONTROL_PURPOSE",
    "MOBILE_HUB_LIST_PURPOSE",
    "PAIRING_REFRESH_GRACE_SECONDS",
    "PAIRING_TOKEN_TTL_SECONDS",
    "create_pairing_token",
    "parse_pairing_token",
    "refresh_pairing_token",
    "rotate_pairing_key",
]
