"""Encrypted OAuth credential persistence for personal SaaS integrations.

[INPUT]
- app.database.models::UserConfig (POS: oauthCredentials row)
- app.services.config.encryption::ConfigEncryptionService (POS: AES-256-GCM encrypt/decrypt)

[OUTPUT]
load/upsert/delete helpers for oauthCredentials UserConfig blob
persist_credentials_locked: encrypt-and-write write-back primitive (shared with MCP OAuth store)
is_oauth_issuer_connected: probe whether an issuer has a stored access token
extract_copilot_base_url: parse API base URL from Copilot JWT proxy-ep field

[POS]
Shared persistence layer for integrations/oauth CRUD and google_workspace_oauth callback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.database.models import UserConfig
from app.services.config.encryption import (
    ConfigEncryptionService,
    get_encryption_service,
)

logger = logging.getLogger(__name__)

CONFIG_KEY = "oauthCredentials"

# Serializes read-modify-write of the shared ``oauthCredentials`` row across
# concurrent writers. Background token refresh (``oauth_refresher``) and manual
# connect/disconnect both merge into the same blob; without a shared lock, a
# slow refresh of one issuer can be overwritten by another issuer's write.
oauth_credentials_lock = asyncio.Lock()

GOOGLE_WORKSPACE_WRITE_SCOPE_MARKERS: tuple[str, ...] = (
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
)

GOOGLE_DRIVE_READ_SCOPE_MARKER = "https://www.googleapis.com/auth/drive.readonly"


def google_workspace_write_enabled(scope: object) -> bool:
    """Return True when stored scope string includes all Google Workspace write scopes."""
    if not isinstance(scope, str) or not scope.strip():
        return False
    return all(marker in scope for marker in GOOGLE_WORKSPACE_WRITE_SCOPE_MARKERS)


def google_drive_read_enabled(scope: object) -> bool:
    """Return True when stored scope string includes Google Drive readonly access."""
    if not isinstance(scope, str) or not scope.strip():
        return False
    return GOOGLE_DRIVE_READ_SCOPE_MARKER in scope


async def google_workspace_drive_read_enabled(db: AsyncSession) -> bool:
    """Return True when Google Workspace OAuth token includes Drive readonly scope."""
    from app.services.agent.oauth_refresher import GOOGLE_WORKSPACE_ISSUER

    row = await load_oauth_credentials_row(db)
    if not row:
        return False
    credentials = decrypt_oauth_credentials(row.config_value, row.is_encrypted)
    cred_val = credentials.get(GOOGLE_WORKSPACE_ISSUER)
    if not isinstance(cred_val, dict) or not cred_val.get("token"):
        return False
    return google_drive_read_enabled(cred_val.get("scope"))


def decrypt_oauth_credentials(
    raw_value: object,
    is_encrypted: bool,
    service: ConfigEncryptionService | None = None,
) -> dict[str, object]:
    """Decrypt and normalize stored OAuth credentials dict."""
    enc = service or get_encryption_service()
    value = raw_value
    if is_encrypted:
        if isinstance(value, str):
            value = enc.decrypt(value)
        elif isinstance(value, dict) and "_cipher" in value:
            value = enc.decrypt(value["_cipher"])

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}

    return value if isinstance(value, dict) else {}


def encrypt_oauth_credentials(
    credentials: dict[str, object],
    service: ConfigEncryptionService | None = None,
    config_key: str = CONFIG_KEY,
) -> tuple[dict[str, object] | str, bool]:
    """Encrypt a credentials dict using the standard encrypt_if_needed API."""
    enc = service or get_encryption_service()
    return enc.encrypt_if_needed(config_key, credentials)


async def load_oauth_credentials_row(db: AsyncSession) -> UserConfig | None:
    return (await db.execute(select(UserConfig).where(UserConfig.config_key == CONFIG_KEY))).scalars().first()


async def persist_credentials_locked(
    db: AsyncSession,
    row: UserConfig | None,
    credentials: dict[str, object],
    config_key: str = CONFIG_KEY,
) -> None:
    """Encrypt and write a UserConfig blob under a caller-held row lock.

    ``row`` is the previously loaded row for ``config_key`` (None when absent);
    re-reading it here would duplicate the SELECT since the caller already
    serialized writes. Used by oauthCredentials writers (upsert/delete/refresh
    merge, guarded by ``oauth_credentials_lock``) and the MCP OAuth token store
    (guarded by its own persist lock).
    """
    service = get_encryption_service()
    final_value, is_encrypted = encrypt_oauth_credentials(credentials, service, config_key)
    if is_encrypted and isinstance(final_value, str):
        final_value = {"_cipher": final_value}

    if row:
        row.config_value = final_value
        row.is_encrypted = is_encrypted
        flag_modified(row, "config_value")
    else:
        db.add(
            UserConfig(
                id=str(uuid.uuid4()),
                config_key=config_key,
                config_value=final_value,
                version="1.0.0",
                last_device_id="sandbox",
                is_encrypted=is_encrypted,
            )
        )
    await db.commit()


async def is_oauth_issuer_connected(db: AsyncSession, issuer: str) -> bool:
    """Return True when oauthCredentials contains a non-empty token for issuer."""
    row = await load_oauth_credentials_row(db)
    if not row:
        return False
    credentials = decrypt_oauth_credentials(row.config_value, row.is_encrypted)
    cred_val = credentials.get(issuer)
    return isinstance(cred_val, dict) and bool(cred_val.get("token"))


async def upsert_oauth_credential(
    db: AsyncSession,
    issuer: str,
    entry: dict[str, object],
) -> None:
    """Insert or update a single issuer entry in oauthCredentials."""
    async with oauth_credentials_lock:
        service = get_encryption_service()
        row = await load_oauth_credentials_row(db)

        credentials: dict[str, object] = {}
        if row:
            credentials = decrypt_oauth_credentials(row.config_value, row.is_encrypted, service)

        credentials[issuer] = entry
        await persist_credentials_locked(db, row, credentials)
        logger.info("Persisted OAuth credentials for issuer '%s'", issuer)


_COPILOT_DEFAULT_BASE_URL = "https://api.individual.githubcopilot.com"


def extract_copilot_base_url(token: str) -> str:
    """Extract API base URL from a GitHub Copilot JWT's proxy-ep field.

    Copilot tokens embed ``proxy-ep=<host>`` which resolves to the correct
    regional API endpoint.  When absent, falls back to the global default.
    """
    match = re.search(r"proxy-ep=([^;]+)", token)
    if match:
        api_host = re.sub(r"^proxy\.", "api.", match.group(1))
        return f"https://{api_host}"
    return _COPILOT_DEFAULT_BASE_URL


async def delete_oauth_credential(db: AsyncSession, issuer: str) -> bool:
    """Remove issuer from oauthCredentials. Returns False if not found."""
    async with oauth_credentials_lock:
        row = await load_oauth_credentials_row(db)
        if not row:
            return False

        service = get_encryption_service()
        credentials = decrypt_oauth_credentials(row.config_value, row.is_encrypted, service)
        if issuer not in credentials:
            return False

        del credentials[issuer]
        await persist_credentials_locked(db, row, credentials)
        logger.info("Deleted OAuth credentials for issuer '%s'", issuer)
        return True
