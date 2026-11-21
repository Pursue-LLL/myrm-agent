"""Per-target hosting credentials stored in UserConfig.

[POS] Encrypt and persist deploy-target API tokens in UserConfig. The operator's platform token is resolved from the
environment at use time and is never copied into a tenant's database.

[INPUT]
- sqlalchemy (POS: async DB session for UserConfig)
- app.services.config.encryption::get_encryption_service/HOSTING_TARGET_CREDENTIALS_PREFIX (POS: business-layer sealing policy; the per-target rows are sealed by key prefix)
- app.services.hosting.targets::credential_config_key/list_hosting_targets/save_hosting_targets (POS: target rows and the config key of a target's credentials)

[OUTPUT]
- save/load/resolve hosting target credentials, legacy Vercel migration, removal of stored platform-token copies
"""

from __future__ import annotations

import json
import logging
import os
import uuid

from myrm_agent_harness.utils.crypto import DecryptionError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.config.deploy_mode import is_sandbox
from app.database.connection import get_session
from app.database.models.config import UserConfig
from app.services.config.encryption import HOSTING_TARGET_CREDENTIALS_PREFIX, get_encryption_service
from app.services.hosting.targets import (
    LEGACY_VERCEL_TARGET_ID,
    credential_config_key,
    get_hosting_target,
    list_hosting_targets,
    save_hosting_targets,
)
from app.services.hosting.types import HostingTarget, TargetCredentialStatus

logger = logging.getLogger(__name__)

VERCEL_CREDENTIALS_KEY = "vercelDeployCredentials"
PLATFORM_TOKEN_ENV = "VERCEL_PLATFORM_TOKEN"


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
        (await db.execute(select(UserConfig).where(UserConfig.config_key == credential_config_key(target_id)))).scalars().first()
    )


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
    key = credential_config_key(target_id)
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
    row = (await db.execute(select(UserConfig).where(UserConfig.config_key == VERCEL_CREDENTIALS_KEY))).scalars().first()
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
    if target and target.provider_type == "http_webhook":
        return {}

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
    if target and target.provider_type == "http_webhook":
        return TargetCredentialStatus(configured=True, platform_available=platform_available)
    if target and target.provider_type == "vercel":
        legacy = await load_legacy_vercel_token(db)
        if legacy or platform_available:
            return TargetCredentialStatus(configured=bool(legacy), platform_available=platform_available)
    return TargetCredentialStatus(configured=False, platform_available=platform_available)


def _stored_token(row: UserConfig) -> str | None:
    try:
        return token_from_credentials(decrypt_credentials(row.config_value, row.is_encrypted))
    except DecryptionError:
        logger.warning("Hosting credentials %s cannot be opened with the current key; left untouched", row.config_key)
        return None


async def _purge_platform_token_copies(db: AsyncSession, platform_token: str) -> None:
    """Delete stored credentials that duplicate the platform token.

    The platform token is an operator secret; a copy in the tenant's database would travel with its backups and
    archives. A target without its own credentials already falls back to the live token, so a copy is never needed.
    Once the copies are gone nothing matches, which makes the sweep idempotent.
    """
    rows = (
        (await db.execute(select(UserConfig).where(UserConfig.config_key.startswith(HOSTING_TARGET_CREDENTIALS_PREFIX))))
        .scalars()
        .all()
    )
    copies = [row for row in rows if _stored_token(row) == platform_token]
    if not copies:
        return
    for row in copies:
        await db.delete(row)
    await db.commit()
    logger.warning("Removed %d stored copies of the platform Vercel token from hosting credentials", len(copies))


async def migrate_legacy_vercel_credentials(db: AsyncSession) -> None:
    """Give a tenant that has Vercel access its default target, and keep the platform token out of its database.

    The user's own legacy token moves into the target's credentials row. The platform token never does: the target
    stays without credentials and publishing resolves the token from the environment.
    """
    platform_token = get_platform_vercel_token()
    if platform_token:
        await _purge_platform_token_copies(db, platform_token)
    legacy_token = await load_legacy_vercel_token(db)
    if not (legacy_token or platform_token):
        return
    if await list_hosting_targets(db):
        return
    target = HostingTarget(
        id=LEGACY_VERCEL_TARGET_ID,
        name="Vercel",
        provider_type="vercel",
        config={},
        is_default=True,
    )
    await save_hosting_targets(db, [target])
    if legacy_token:
        await save_target_credentials(db, target.id, {"token": legacy_token})


async def has_any_hosting_credentials() -> bool:
    if get_platform_vercel_token():
        return True
    async with get_session() as db:
        from app.services.hosting.targets import list_hosting_targets

        if await list_hosting_targets(db):
            return True
        return await load_legacy_vercel_token(db) is not None
