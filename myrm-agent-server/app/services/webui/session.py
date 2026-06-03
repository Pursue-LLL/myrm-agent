"""
[INPUT]
- app.config.settings::settings.database.state_dir (POS: workspace root for webui secrets)

[OUTPUT]
- SESSION_COOKIE_NAME, SESSION_TTL_SECONDS: WebUI session cookie contract
- create_session_value, parse_session_value: signed session payload helpers
- rotate_session_signing_key: invalidate all outstanding WebUI session cookies

[POS]
WebUI browser session signing (HMAC cookie, local/remote single-tenant only).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import secrets
import time
from pathlib import Path

from app.config.settings import settings

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "myrm_webui_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 7
_KEY_FILE = Path("webui") / "session_key"


def _session_key_path() -> Path:
    return Path(settings.database.state_dir) / _KEY_FILE


def _load_or_create_key() -> bytes:
    path = _session_key_path()
    if path.is_file():
        raw = path.read_bytes()
        if len(raw) >= 32:
            return raw[:32]
    return rotate_session_signing_key()


def rotate_session_signing_key() -> bytes:
    """Rotate HMAC signing key so all existing WebUI session cookies become invalid."""
    path = _session_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    path.write_bytes(key)
    path.chmod(0o600)
    return key


def _sign(payload: str) -> str:
    key = _load_or_create_key()
    digest = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def create_session_value(username: str) -> str:
    expires_at = int(time.time()) + SESSION_TTL_SECONDS
    body = json.dumps({"u": username, "exp": expires_at}, separators=(",", ":"))
    body_b64 = base64.urlsafe_b64encode(body.encode("utf-8")).decode("ascii").rstrip("=")
    signature = _sign(body_b64)
    return f"{body_b64}.{signature}"


def parse_session_value(value: str | None) -> str | None:
    if not value or "." not in value:
        return None
    body_b64, signature = value.rsplit(".", 1)
    if not hmac.compare_digest(_sign(body_b64), signature):
        return None
    try:
        padded = body_b64 + "=" * (-len(body_b64) % 4)
        body = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (json.JSONDecodeError, ValueError, binascii.Error):
        return None
    username = body.get("u")
    expires_at = body.get("exp")
    if not isinstance(username, str) or not isinstance(expires_at, int):
        return None
    if expires_at < int(time.time()):
        return None
    return username


__all__ = [
    "SESSION_COOKIE_NAME",
    "SESSION_TTL_SECONDS",
    "create_session_value",
    "parse_session_value",
    "rotate_session_signing_key",
]
