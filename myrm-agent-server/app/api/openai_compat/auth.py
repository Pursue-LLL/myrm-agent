"""OpenAI-compatible API authentication.

[INPUT] app.database.models.api_key::APIKey (POS: API Key ORM model)
[INPUT] app.services.config.service::config_service (POS: Config service for proxy settings)
[OUTPUT] verify_api_key: FastAPI dependency for Bearer Token validation
[POS] Dual-mode authentication for /v1/* endpoints:
  - Strict mode (default): validates API key hash against the database
  - Open mode (proxy): any non-empty Bearer token accepted when proxySettings.auth.allow_any_key is True
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from fastapi import Header, HTTPException
from sqlalchemy import select, update

from app.database.connection import get_session
from app.database.models.api_key import APIKey

logger = logging.getLogger(__name__)

_OPEN_KEY_PREFIX = "proxy-open"
_OPEN_AUTH_CACHE_TTL = 10.0  # seconds
_open_auth_cache: tuple[float, bool] = (0.0, False)


def _hash_key(raw_key: str) -> str:
    """Compute SHA-256 hash of API key for secure storage comparison."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def _is_open_auth_enabled() -> bool:
    """Check if proxy open auth mode is enabled (cached 10s to avoid per-request DB hits)."""
    import time

    global _open_auth_cache  # noqa: PLW0603

    cached_at, cached_value = _open_auth_cache
    if time.monotonic() - cached_at < _OPEN_AUTH_CACHE_TTL:
        return cached_value

    result = False
    try:
        from app.services.config.service import config_service

        record = await config_service.get("proxySettings")
        if record is not None:
            value = record.value if hasattr(record, "value") else record
            if isinstance(value, dict):
                auth = value.get("auth", {})
                if isinstance(auth, dict):
                    result = bool(auth.get("allow_any_key", False))
    except Exception:
        logger.debug("Failed to check proxy open auth mode", exc_info=True)

    _open_auth_cache = (time.monotonic(), result)
    return result


def _extract_bearer_token(authorization: str | None) -> str:
    """Extract and validate Bearer token from Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail={"error": {"message": "Missing Authorization header", "type": "auth_error", "code": "missing_api_key"}},
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "message": "Invalid Authorization format. Expected: Bearer sk-...",
                    "type": "auth_error",
                    "code": "invalid_format",
                }
            },
        )

    raw_key = authorization[7:].strip()
    if not raw_key:
        raise HTTPException(
            status_code=401,
            detail={"error": {"message": "Empty API key", "type": "auth_error", "code": "empty_key"}},
        )
    return raw_key


async def _verify_strict(raw_key: str) -> str:
    """Strict verification: validate key hash against database."""
    key_hash = _hash_key(raw_key)

    async with get_session() as session:
        result = await session.execute(select(APIKey).where(APIKey.key_hash == key_hash))
        api_key = result.scalar_one_or_none()

        if api_key is None:
            raise HTTPException(
                status_code=401,
                detail={"error": {"message": "Invalid API key", "type": "auth_error", "code": "invalid_key"}},
            )

        if not api_key.is_active:
            raise HTTPException(
                status_code=403,
                detail={"error": {"message": "API key has been revoked", "type": "auth_error", "code": "key_revoked"}},
            )

        if api_key.expires_at:
            expires = api_key.expires_at
            now = datetime.now(UTC)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if expires < now:
                raise HTTPException(
                    status_code=403,
                    detail={"error": {"message": "API key has expired", "type": "auth_error", "code": "key_expired"}},
                )

        await session.execute(
            update(APIKey)
            .where(APIKey.id == api_key.id)
            .values(last_used_at=datetime.now(UTC), usage_count=APIKey.usage_count + 1)
        )
        await session.commit()

        return api_key.key_prefix


async def verify_api_key(
    authorization: str | None = Header(None),
) -> str:
    """FastAPI dependency: validate Bearer token from Authorization header.

    Returns the key_prefix for audit logging.
    In open auth mode (proxy), any non-empty Bearer token is accepted.
    In strict mode (default), validates against the database.
    """
    raw_key = _extract_bearer_token(authorization)

    if await _is_open_auth_enabled():
        return _OPEN_KEY_PREFIX

    return await _verify_strict(raw_key)
