"""OpenAI-compatible API authentication.

[INPUT] app.database.models.api_key::APIKey (POS: API Key ORM model)
[OUTPUT] verify_api_key: FastAPI dependency for Bearer Token validation
[POS] Strict authentication for /v1/* endpoints: validates API key hash against the database.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from fastapi import Header, HTTPException
from sqlalchemy import select, update

from app.database.connection import get_session
from app.database.models.api_key import APIKey


def _hash_key(raw_key: str) -> str:
    """Compute SHA-256 hash of API key for secure storage comparison."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


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
    """
    raw_key = _extract_bearer_token(authorization)
    return await _verify_strict(raw_key)
