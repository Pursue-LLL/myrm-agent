"""OAuth Credential Management API.

[INPUT]
app.database.connection::get_db (POS: 异步数据库会话工厂)
app.database.models::UserConfig (POS: 用户配置 ORM 模型)
app.services.config.encryption::get_encryption_service (POS: AES-256-GCM 加密服务单例)
app.services.memory.integration_memory::get_integration_memory_service (POS: 集成记忆服务单例)

[OUTPUT]
OAuth credential CRUD endpoints: GET /oauth, POST /oauth/{issuer}, DELETE /oauth/{issuer}
DELETE 支持 clear_synced_memory 参数，断开时可选清除该 provider 已同步的记忆数据。

[POS]
OAuth 凭证管理 API。提供个人 SaaS 集成凭证的加密存储、查询和撤销，支持断开时可选清除同步数据。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.services.config.encryption import get_encryption_service
from app.services.integrations.oauth_store import (
    decrypt_oauth_credentials,
    load_oauth_credentials_row,
    upsert_oauth_credential,
)
from app.services.integrations.oauth_store import (
    delete_oauth_credential as remove_oauth_credential,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class OAuthCredentialItem(BaseModel):
    issuer: str
    user_id: str | None = None
    scope: str | None = None
    expires_at: float | None = None
    connected: bool = False


class SaveOAuthCredentialPayload(BaseModel):
    token: str
    user_id: str | None = None
    scope: str | None = None
    expires_at: float | None = None


@router.get("", response_model=list[OAuthCredentialItem])
async def list_oauth_credentials(
    db: AsyncSession = Depends(get_db),
) -> list[OAuthCredentialItem]:
    """List all active personal OAuth / SaaS integrations."""
    row = await load_oauth_credentials_row(db)
    if not row:
        return []

    credentials = decrypt_oauth_credentials(row.config_value, row.is_encrypted, get_encryption_service())

    return [
        OAuthCredentialItem(
            issuer=issuer,
            user_id=val.get("user_id"),
            scope=val.get("scope"),
            expires_at=val.get("expires_at"),
            connected=bool(val.get("token")),
        )
        for issuer, val in credentials.items()
        if isinstance(val, dict)
    ]


@router.delete("/{issuer}")
async def delete_oauth_credential_endpoint(
    issuer: str,
    clear_synced_memory: bool = False,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Disauthorize / delete OAuth credential for a platform.

    Args:
        clear_synced_memory: If True, also removes all integration memory trees
                            synced from this provider.
    """
    deleted = await remove_oauth_credential(db, issuer)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Integration '{issuer}' is not connected")

    trees_removed = 0
    if clear_synced_memory:
        from app.services.memory.integration_memory import get_integration_memory_service

        svc = await get_integration_memory_service()
        if svc:
            trees_removed = await svc.remove_trees_by_provider(issuer)

    logger.info("Deleted OAuth integration for '%s' (trees_removed=%d)", issuer, trees_removed)
    return {
        "status": "success",
        "message": f"Successfully deleted integration '{issuer}'",
        "trees_removed": trees_removed,
    }


@router.post("/{issuer}")
async def save_oauth_credential(
    issuer: str,
    payload: SaveOAuthCredentialPayload,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Manually add or connect personal token (PAT/OAuth token) for an integration."""
    await upsert_oauth_credential(
        db,
        issuer,
        {
            "token": payload.token,
            "user_id": payload.user_id or "",
            "scope": payload.scope or "",
            "expires_at": payload.expires_at,
        },
    )
    logger.info("Successfully saved OAuth integration credentials for '%s'", issuer)
    return {"status": "success", "message": f"Successfully saved integration '{issuer}'"}
