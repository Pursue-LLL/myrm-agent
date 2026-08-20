"""Shared unlock-cookie mechanics for password-protected share links.

[INPUT]
- app.core.security.share.share_hmac (POS: HMAC signing primitives)

[OUTPUT]
- unlock_cookie_name / build_unlock_credential / parse_unlock_credential /
  attach_unlock_cookie: consumed by artifact and chat public share endpoints

[POS]
Centralizes the security-sensitive cookie attributes (HttpOnly / SameSite /
Secure, per-share cookie name, 60-second minimum-TTL rule) so the artifact and
chat share modules can never drift apart on security parameters. Claims
marshalling stays in each caller; only the stateless credential mechanics are
shared.
"""

from __future__ import annotations

import hashlib
import time

from fastapi import Response

from app.core.security.share.share_hmac import (
    create_share_token,
    parse_share_token,
)

# Below this remaining TTL no unlock credential is issued: the share would
# expire before the viewer finishes with it, and serving content directly
# avoids a redirect loop.
_MIN_UNLOCK_TTL_SECONDS = 60
_MAX_UNLOCK_TTL_SECONDS = 30 * 24 * 3600


def unlock_cookie_name(cookie_prefix: str, token: str) -> str:
    """Per-share cookie name so concurrent password shares never collide.

    A single fixed cookie name would be overwritten when a user opens several
    password-protected shares, causing later asset requests to authorize
    against the wrong share's credentials.
    """
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return f"{cookie_prefix}_{digest}"


def build_unlock_credential(
    payload: dict[str, object],
    *,
    salt: str,
    exp: int,
) -> str | None:
    """Mint a short-lived HMAC credential for an unlocked share.

    Returns ``None`` when the share is too close to expiry to warrant a
    credential (less than ``_MIN_UNLOCK_TTL_SECONDS`` remaining).
    """
    remaining = exp - int(time.time())
    if remaining < _MIN_UNLOCK_TTL_SECONDS:
        return None
    credential, _ = create_share_token(
        payload,
        salt=salt,
        ttl_seconds=remaining,
        max_ttl_seconds=_MAX_UNLOCK_TTL_SECONDS,
    )
    return credential


def parse_unlock_credential(value: str, *, salt: str) -> dict[str, object] | None:
    """Recover the raw signed payload from an unlock credential, or ``None``."""
    return parse_share_token(value, salt=salt)


def attach_unlock_cookie(
    response: Response,
    *,
    cookie_prefix: str,
    salt: str,
    path: str,
    payload: dict[str, object],
    exp: int,
    token: str,
    password: str | None,
    secure: bool,
) -> bool:
    """Set the unlock cookie after a correct password unlock.

    Returns ``True`` when the cookie was issued (share has enough remaining
    TTL), ``False`` when it was skipped (no password or share about to expire).
    """
    if not password:
        return False
    credential = build_unlock_credential(payload, salt=salt, exp=exp)
    if credential is None:
        return False
    response.set_cookie(
        key=unlock_cookie_name(cookie_prefix, token),
        value=credential,
        max_age=max(0, exp - int(time.time())),
        path=path,
        httponly=True,
        samesite="strict",
        secure=secure,
    )
    return True
