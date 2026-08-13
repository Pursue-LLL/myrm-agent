"""Shared HMAC signing primitives for stateless share tokens.

[INPUT]
- app.config.settings::settings (POS: signing key material)

[OUTPUT]
- create_share_token / sign_share_token / parse_share_token / is_password_protected
- sign_share_token: sign with an explicit ``exp`` (used to rebuild persisted
  links from registry fields); create_share_token derives exp from ttl

[POS]
Common HMAC-SHA256 signing layer used by both artifact and chat share token
modules. Supports optional password-protected tokens via key derivation.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.config.settings import settings

_TOKEN_VERSION = 1


def _signing_secret(salt: str) -> bytes:
    """Derive a per-domain signing secret using *salt* (e.g. 'artifact-share').

    Salt is always mixed into the key via HMAC so that tokens from different
    domains (artifact-share vs chat-share) are never cross-verifiable.
    """
    base_key: bytes | None = None
    for candidate in (
        settings.config_encryption_key.get_secret_value(),
        settings.internal_service_key.get_secret_value(),
        settings.sandbox_api_key.get_secret_value(),
    ):
        if candidate and candidate.strip():
            base_key = candidate.strip().encode("utf-8")
            break
    if base_key is None:
        seed = (settings.database.state_dir or "myrm-local").encode("utf-8")
        base_key = hashlib.sha256(seed).digest()
    return hmac.new(base_key, salt.encode("utf-8"), hashlib.sha256).digest()


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def b64url_decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded + padding)


def _derive_key(salt: str, password: str | None) -> bytes:
    """Return signing key, optionally strengthened with a password hash."""
    key = _signing_secret(salt)
    if password and password.strip():
        pw_hash = hashlib.sha256(password.strip().encode("utf-8")).digest()
        key = hashlib.sha256(key + pw_hash).digest()
    return key


def sign_share_token(
    payload: dict[str, Any],
    *,
    salt: str,
    exp: int,
    password: str | None = None,
) -> str:
    """Sign a token with an explicit expiry (used to rebuild persisted links).

    Mirrors ``create_share_token`` but pins ``exp`` instead of deriving it from
    ``time.time()``, so a link can be reconstructed from registry fields.
    """
    token_payload: dict[str, Any] = {"v": _TOKEN_VERSION, **payload, "exp": exp}
    if password and password.strip():
        token_payload["p"] = 1

    body = b64url_encode(json.dumps(token_payload, separators=(",", ":")).encode("utf-8"))
    key = _derive_key(salt, password)
    sig = hmac.new(key, body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def create_share_token(
    payload: dict[str, Any],
    *,
    salt: str,
    ttl_seconds: int,
    max_ttl_seconds: int,
    password: str | None = None,
) -> tuple[str, int]:
    """Create an HMAC-signed share token. Returns ``(token, expires_at_unix)``."""
    ttl_seconds = max(60, min(ttl_seconds, max_ttl_seconds))
    exp = int(time.time()) + ttl_seconds
    return sign_share_token(payload, salt=salt, exp=exp, password=password), exp


def parse_share_token(
    token: str,
    *,
    salt: str,
    password: str | None = None,
) -> dict[str, Any] | None:
    """Verify signature, version, and expiry. Returns raw payload dict or ``None``."""
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)

    try:
        raw: dict[str, Any] = json.loads(b64url_decode(body))
    except (json.JSONDecodeError, ValueError):
        return None

    if raw.get("v") != _TOKEN_VERSION:
        return None

    is_protected = raw.get("p") == 1
    if is_protected and not (password and password.strip()):
        return None

    key = _derive_key(salt, password if is_protected else None)
    expected = hmac.new(key, body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None

    exp = raw.get("exp")
    if not isinstance(exp, int) or exp < int(time.time()):
        return None

    return raw


def is_password_protected(token: str) -> bool:
    """Check if a token requires a password without full verification."""
    if not token or "." not in token:
        return False
    body = token.rsplit(".", 1)[0]
    try:
        raw = json.loads(b64url_decode(body))
        return raw.get("p") == 1
    except (json.JSONDecodeError, ValueError):
        return False
