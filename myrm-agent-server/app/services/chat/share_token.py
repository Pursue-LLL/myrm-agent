"""Stateless HMAC tokens for time-limited public conversation share links.

[INPUT]
- app.core.security.share.share_hmac (POS: shared HMAC signing primitives)

[OUTPUT]
- create_chat_share_token / parse_chat_share_token
- rebuild_chat_share_token: reconstruct an unprotected token from a persisted
  expiry (deterministic HMAC → same payload + expiry yields the same token),
  so the GUI can display the current share link without storing the raw token
- ChatShareClaims dataclass

[POS]
Delegates signing to the shared share_hmac module; adds chat-specific
payload fields. No DB storage needed for the token itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.security.share.share_hmac import create_share_token, parse_share_token, sign_share_token

_SALT = "chat-share"
_DEFAULT_TTL_SECONDS = 7 * 24 * 3600
_MAX_TTL_SECONDS = 30 * 24 * 3600


@dataclass(frozen=True)
class ChatShareClaims:
    chat_id: str
    exp: int
    password_protected: bool = False


def create_chat_share_token(
    chat_id: str,
    *,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    password: str | None = None,
) -> tuple[str, int]:
    """Return (token, expires_at_unix)."""
    return create_share_token(
        {"cid": chat_id},
        salt=_SALT,
        ttl_seconds=ttl_seconds,
        max_ttl_seconds=_MAX_TTL_SECONDS,
        password=password,
    )


def parse_chat_share_token(
    token: str,
    *,
    password: str | None = None,
) -> ChatShareClaims | None:
    """Verify signature and expiry; return None when invalid."""
    raw = parse_share_token(token, salt=_SALT, password=password)
    if raw is None:
        return None
    chat_id = raw.get("cid")
    exp = raw.get("exp")
    if not isinstance(chat_id, str) or not isinstance(exp, int):
        return None
    return ChatShareClaims(
        chat_id=chat_id,
        exp=exp,
        password_protected=raw.get("p") == 1,
    )


def rebuild_chat_share_token(chat_id: str, *, expires_at_unix: int) -> str:
    """Reconstruct an unprotected share token from a persisted expiry.

    Tokens are deterministic (same payload + expiry yields the same token), so
    the link can be rebuilt without storing the raw token. Password-protected
    shares cannot be rebuilt here: the password is never persisted.
    """
    return sign_share_token({"cid": chat_id}, salt=_SALT, exp=expires_at_unix)
