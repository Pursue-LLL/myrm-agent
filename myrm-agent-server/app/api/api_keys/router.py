"""API Key CRUD endpoints.

[INPUT]
- app.database.models.api_key::APIKey (POS: API Key ORM model)
- app.api.openai_compat.auth::_hash_key (POS: key hashing utility)

[OUTPUT]
- create_api_key, list_api_keys, revoke_api_key, delete_api_key

[POS]
GUI-facing CRUD for managing API keys. The plaintext key is only
returned once during creation. All subsequent operations reference
keys by ID or prefix.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update

from app.api.openai_compat.auth import _hash_key
from app.database.connection import get_session
from app.database.models.api_key import APIKey

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api-keys", tags=["api-keys"])

_KEY_PREFIX = "sk-myrm-"
_KEY_RANDOM_BYTES = 32


def _generate_api_key() -> str:
    """Generate a secure random API key with myrm prefix."""
    random_part = secrets.token_urlsafe(_KEY_RANDOM_BYTES)
    return f"{_KEY_PREFIX}{random_part}"


class CreateKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)
    note: str | None = None


class CreateKeyResponse(BaseModel):
    """Response containing the full key (shown only once)."""

    id: int
    name: str
    key: str
    key_prefix: str
    expires_at: datetime | None
    created_at: datetime


class KeyInfo(BaseModel):
    """Key info without the secret."""

    id: int
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: datetime | None
    usage_count: int
    expires_at: datetime | None
    note: str | None
    created_at: datetime


@router.post("", response_model=CreateKeyResponse)
async def create_api_key(body: CreateKeyRequest) -> CreateKeyResponse:
    """Create a new API key. The full key is returned only in this response."""
    raw_key = _generate_api_key()
    key_hash = _hash_key(raw_key)
    key_prefix = raw_key[:12]

    expires_at = None
    if body.expires_in_days:
        from datetime import timedelta

        expires_at = datetime.now(UTC) + timedelta(days=body.expires_in_days)

    async with get_session() as session:
        api_key = APIKey(
            name=body.name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            is_active=True,
            expires_at=expires_at,
            note=body.note,
        )
        session.add(api_key)
        await session.commit()
        await session.refresh(api_key)

        return CreateKeyResponse(
            id=api_key.id,
            name=api_key.name,
            key=raw_key,
            key_prefix=key_prefix,
            expires_at=expires_at,
            created_at=api_key.created_at,
        )


@router.get("", response_model=list[KeyInfo])
async def list_api_keys() -> list[KeyInfo]:
    """List all API keys (without secrets)."""
    async with get_session() as session:
        result = await session.execute(
            select(APIKey).order_by(APIKey.created_at.desc())
        )
        keys = result.scalars().all()

        return [
            KeyInfo(
                id=k.id,
                name=k.name,
                key_prefix=k.key_prefix,
                is_active=k.is_active,
                last_used_at=k.last_used_at,
                usage_count=k.usage_count,
                expires_at=k.expires_at,
                note=k.note,
                created_at=k.created_at,
            )
            for k in keys
        ]


@router.patch("/{key_id}/revoke")
async def revoke_api_key(key_id: int) -> dict[str, str]:
    """Revoke an API key (soft-disable, preserves history)."""
    async with get_session() as session:
        result = await session.execute(
            update(APIKey)
            .where(APIKey.id == key_id)
            .values(is_active=False)
            .returning(APIKey.id)
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="API key not found")
        await session.commit()
        return {"status": "revoked"}


@router.delete("/{key_id}")
async def delete_api_key(key_id: int) -> dict[str, str]:
    """Permanently delete an API key."""
    async with get_session() as session:
        result = await session.execute(
            delete(APIKey).where(APIKey.id == key_id).returning(APIKey.id)
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="API key not found")
        await session.commit()
        return {"status": "deleted"}
