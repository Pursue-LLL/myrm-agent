"""Vercel deploy credential resolution and availability checks.

[INPUT]
- app.services.config.encryption::get_encryption_service (POS: UserConfig 敏感字段加解密)
- app.config.deploy_mode::is_sandbox (POS: 部署模式判定)
- app.database.models.config::UserConfig (POS: 用户配置持久化)

[OUTPUT]
- decrypt_vercel_credentials / resolve_vercel_token / save_vercel_credentials / has_deploy_credentials / load_vercel_credentials_row

[POS]
Vercel 部署凭证 SSOT：REST deploy_api 与 Agent 工具共用 token 解析与可用性门控。
"""

from __future__ import annotations

import json
import os
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.config.deploy_mode import is_sandbox
from app.database.connection import get_session
from app.database.models.config import UserConfig
from app.services.config.encryption import get_encryption_service

VERCEL_CREDENTIALS_KEY = "vercelDeployCredentials"
PLATFORM_TOKEN_ENV = "VERCEL_PLATFORM_TOKEN"


def decrypt_vercel_credentials(raw_value: object, is_encrypted: bool) -> dict[str, object]:
    """Decrypt and parse stored Vercel credential payload from UserConfig."""
    service = get_encryption_service()
    value = raw_value
    if is_encrypted:
        if isinstance(value, str):
            value = service.decrypt(value)
        elif isinstance(value, dict) and "_cipher" in value:
            cipher = value["_cipher"]
            if isinstance(cipher, str):
                value = service.decrypt(cipher)

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}

    return value if isinstance(value, dict) else {}


def get_platform_vercel_token() -> str | None:
    """Return platform-injected Vercel token in sandbox mode, if configured."""
    if not is_sandbox():
        return None
    token = os.environ.get(PLATFORM_TOKEN_ENV, "").strip()
    return token or None


def token_from_credentials_dict(credentials: dict[str, object]) -> str | None:
    """Extract a non-empty token string from decrypted credentials dict."""
    token = credentials.get("token")
    if isinstance(token, str) and token.strip():
        return token.strip()
    return None


async def load_vercel_credentials_row(db: AsyncSession) -> UserConfig | None:
    """Return the UserConfig row for stored Vercel deploy credentials, if any."""
    return (
        await db.execute(select(UserConfig).where(UserConfig.config_key == VERCEL_CREDENTIALS_KEY))
    ).scalars().first()


async def load_stored_vercel_token(db: AsyncSession) -> str | None:
    """Load user BYOK Vercel token from UserConfig, if configured."""
    row = await load_vercel_credentials_row(db)
    if not row:
        return None
    credentials = decrypt_vercel_credentials(row.config_value, row.is_encrypted)
    return token_from_credentials_dict(credentials)


async def resolve_vercel_token(db: AsyncSession, request_token: str = "") -> str:
    """Resolve Vercel token: request body → stored BYOK → platform env."""
    token = request_token.strip()
    if token:
        return token

    stored = await load_stored_vercel_token(db)
    if stored:
        return stored

    platform_token = get_platform_vercel_token()
    if platform_token:
        return platform_token

    raise RuntimeError(
        "Vercel token not configured. "
        "Configure it in artifact deploy settings or agent deploy credentials."
    )


async def has_deploy_credentials() -> bool:
    """Return True when user BYOK or platform Vercel token is available."""
    if get_platform_vercel_token():
        return True

    async with get_session() as db:
        return await load_stored_vercel_token(db) is not None


async def save_vercel_credentials(
    db: AsyncSession,
    token: str,
    *,
    device_id: str = "webui",
) -> dict[str, str]:
    """Persist Vercel deploy token in UserConfig with encryption."""
    service = get_encryption_service()
    value: dict[str, object] = {"token": token.strip()}
    stored_value, is_encrypted = service.encrypt_if_needed(VERCEL_CREDENTIALS_KEY, value)
    if is_encrypted and isinstance(stored_value, str):
        stored_value = {"_cipher": stored_value}

    row = await load_vercel_credentials_row(db)
    if row:
        row.config_value = stored_value
        row.is_encrypted = is_encrypted
        flag_modified(row, "config_value")
    else:
        db.add(
            UserConfig(
                id=str(uuid.uuid4()),
                config_key=VERCEL_CREDENTIALS_KEY,
                config_value=stored_value,
                version="1.0.0",
                last_device_id=device_id,
                is_encrypted=is_encrypted,
            )
        )

    await db.commit()
    return {"status": "success", "message": "Vercel credentials saved"}
