"""Per-target hosting credentials stored in UserConfig.

[POS] Encrypt and persist deploy-target API tokens in UserConfig.

[INPUT]
- sqlalchemy (POS: async DB session for UserConfig)
- app.services.config.encryption (POS: AES-GCM field encryption)

[OUTPUT]
- save/load/delete hosting target credentials with legacy Vercel migration
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
from app.services.hosting.targets import LEGACY_VERCEL_TARGET_ID, get_hosting_target, list_hosting_targets, save_hosting_targets
from app.services.hosting.types import TargetCredentialStatus

VERCEL_CREDENTIALS_KEY = "vercelDeployCredentials"
PLATFORM_TOKEN_ENV = "VERCEL_PLATFORM_TOKEN"


def _credential_key(target_id: str) -> str:
    return f"hostingTargetCredentials:{target_id}"


def decrypt_credentials(raw_value: object, is_encrypted: bool) -> dict[str, object]:
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
    if not is_sandbox():
        return None
    token = os.environ.get(PLATFORM_TOKEN_ENV, "").strip()
    return token or None


def token_from_credentials(credentials: dict[str, object]) -> str | None:
    token = credentials.get("token")
    if isinstance(token, str) and token.strip():
        return token.strip()
    return None


async def load_credentials_row(db: AsyncSession, target_id: str) -> UserConfig | None:
    return (
        await db.execute(select(UserConfig).where(UserConfig.config_key == _credential_key(target_id)))
    ).scalars().first()


async def load_target_credentials(db: AsyncSession, target_id: str) -> dict[str, object]:
    row = await load_credentials_row(db, target_id)
    if not row:
        return {}
    return decrypt_credentials(row.config_value, row.is_encrypted)


async def save_target_credentials(
    db: AsyncSession,
    target_id: str,
    credentials: dict[str, object],
    *,
    device_id: str = "webui",
) -> dict[str, str]:
    service = get_encryption_service()
    key = _credential_key(target_id)
    stored_value, is_encrypted = service.encrypt_if_needed(key, credentials)
    if is_encrypted and isinstance(stored_value, str):
        stored_value = {"_cipher": stored_value}
    row = await load_credentials_row(db, target_id)
    if row:
        row.config_value = stored_value
        row.is_encrypted = is_encrypted
        flag_modified(row, "config_value")
    else:
        db.add(
            UserConfig(
                id=str(uuid.uuid4()),
                config_key=key,
                config_value=stored_value,
                version="1.0.0",
                last_device_id=device_id,
                is_encrypted=is_encrypted,
            )
        )
    await db.commit()
    return {"status": "success", "message": "Credentials saved"}


async def load_legacy_vercel_token(db: AsyncSession) -> str | None:
    row = (
        await db.execute(select(UserConfig).where(UserConfig.config_key == VERCEL_CREDENTIALS_KEY))
    ).scalars().first()
    if not row:
        return None
    credentials = decrypt_credentials(row.config_value, row.is_encrypted)
    return token_from_credentials(credentials)


async def resolve_target_credentials(
    db: AsyncSession,
    target_id: str,
    *,
    request_token: str = "",
) -> dict[str, object]:
    token = request_token.strip()
    if token:
        return {"token": token}

    creds = await load_target_credentials(db, target_id)
    if creds:
        return creds

    target = await get_hosting_target(db, target_id)
    if target and target.provider_type == "vercel":
        legacy = await load_legacy_vercel_token(db)
        if legacy:
            return {"token": legacy}
        platform = get_platform_vercel_token()
        if platform:
            return {"token": platform}

    raise RuntimeError("Hosting credentials not configured for this target.")


async def get_target_credential_status(db: AsyncSession, target_id: str) -> TargetCredentialStatus:
    target = await get_hosting_target(db, target_id)
    platform_available = bool(target and target.provider_type == "vercel" and get_platform_vercel_token())
    creds = await load_target_credentials(db, target_id)
    if creds:
        return TargetCredentialStatus(configured=True, platform_available=platform_available)
    if target and target.provider_type == "vercel":
        legacy = await load_legacy_vercel_token(db)
        if legacy or platform_available:
            return TargetCredentialStatus(configured=bool(legacy), platform_available=platform_available)
    return TargetCredentialStatus(configured=False, platform_available=platform_available)


async def migrate_legacy_vercel_credentials(db: AsyncSession) -> None:
    legacy_token = await load_legacy_vercel_token(db)
    token = legacy_token or get_platform_vercel_token()
    if not token:
        return
    targets = await list_hosting_targets(db)
    if targets:
        return
    from app.services.hosting.types import HostingTarget

    target = HostingTarget(
        id=LEGACY_VERCEL_TARGET_ID,
        name="Vercel",
        provider_type="vercel",
        config={},
        is_default=True,
    )
    await save_hosting_targets(db, [target])
    await save_target_credentials(db, target.id, {"token": token})


async def has_any_hosting_credentials() -> bool:
    if get_platform_vercel_token():
        return True
    async with get_session() as db:
        from app.services.hosting.targets import list_hosting_targets

        if await list_hosting_targets(db):
            return True
        return await load_legacy_vercel_token(db) is not None
