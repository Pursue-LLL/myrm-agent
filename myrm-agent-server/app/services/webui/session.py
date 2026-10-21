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
import os
import re
import secrets
import time
from pathlib import Path

from app.config.settings import settings

logger = logging.getLogger(__name__)

_DEFAULT_SESSION_COOKIE_NAME = "myrm_webui_session"
_COOKIE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _session_cookie_name() -> str:
    configured = os.environ.get("WEBUI_SESSION_COOKIE_NAME", "").strip()
    if not configured:
        return _DEFAULT_SESSION_COOKIE_NAME
    if not _COOKIE_NAME_RE.fullmatch(configured):
        raise RuntimeError("WEBUI_SESSION_COOKIE_NAME must be 1-64 URL-safe characters")
    return configured


SESSION_COOKIE_NAME = _session_cookie_name()
SESSION_TTL_SECONDS = 60 * 60 * 24 * 7
REMOTE_IDLE_TTL_SECONDS = 60 * 30
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


def create_session_value(username: str, *, last_activity: int | None = None) -> str:
    now = int(time.time())
    last = last_activity if last_activity is not None else now
    expires_at = now + SESSION_TTL_SECONDS
    body = json.dumps({"u": username, "exp": expires_at, "last": last}, separators=(",", ":"))
    body_b64 = base64.urlsafe_b64encode(body.encode("utf-8")).decode("ascii").rstrip("=")
    signature = _sign(body_b64)
    return f"{body_b64}.{signature}"


def parse_session_value(
    value: str | None,
    *,
    max_idle_seconds: int | None = None,
) -> str | None:
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
    last_activity = body.get("last")
    if not isinstance(username, str) or not isinstance(expires_at, int):
        return None
    now = int(time.time())
    if expires_at < now:
        return None
    if max_idle_seconds is not None:
        idle_anchor = last_activity if isinstance(last_activity, int) else expires_at
        if now - idle_anchor > max_idle_seconds:
            return None
    return username


__all__ = [
    "SESSION_COOKIE_NAME",
    "SESSION_TTL_SECONDS",
    "REMOTE_IDLE_TTL_SECONDS",
    "create_session_value",
    "parse_session_value",
    "rotate_session_signing_key",
]
