"""Encrypted OAuth credential persistence for personal SaaS integrations.

[INPUT]
- app.database.models::UserConfig (POS: oauthCredentials row)
- app.services.config.encryption::ConfigEncryptionService (POS: AES-256-GCM encrypt/decrypt)

[OUTPUT]
load/upsert/delete helpers for oauthCredentials UserConfig blob
is_oauth_issuer_connected: probe whether an issuer has a stored access token

[POS]
Shared persistence layer for integrations/oauth CRUD and google_workspace_oauth callback.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.database.models import UserConfig
from app.services.config.encryption import ConfigEncryptionService, get_encryption_service

logger = logging.getLogger(__name__)

CONFIG_KEY = "oauthCredentials"


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
) -> tuple[dict[str, object] | str, bool]:
    """Encrypt credentials dict using the standard encrypt_if_needed API."""
    enc = service or get_encryption_service()
    return enc.encrypt_if_needed(CONFIG_KEY, credentials)


async def load_oauth_credentials_row(db: AsyncSession) -> UserConfig | None:
    return (await db.execute(select(UserConfig).where(UserConfig.config_key == CONFIG_KEY))).scalars().first()


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
    entry: dict[str, Any],
) -> None:
    """Insert or update a single issuer entry in oauthCredentials."""
    service = get_encryption_service()
    row = await load_oauth_credentials_row(db)

    credentials: dict[str, object] = {}
    if row:
        credentials = decrypt_oauth_credentials(row.config_value, row.is_encrypted, service)

    credentials[issuer] = entry

    final_value, is_encrypted = encrypt_oauth_credentials(credentials, service)
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
                config_key=CONFIG_KEY,
                config_value=final_value,
                version="1.0.0",
                last_device_id="sandbox",
                is_encrypted=is_encrypted,
            )
        )

    await db.commit()
    logger.info("Persisted OAuth credentials for issuer '%s'", issuer)


async def delete_oauth_credential(db: AsyncSession, issuer: str) -> bool:
    """Remove issuer from oauthCredentials. Returns False if not found."""
    row = await load_oauth_credentials_row(db)
    if not row:
        return False

    service = get_encryption_service()
    credentials = decrypt_oauth_credentials(row.config_value, row.is_encrypted, service)
    if issuer not in credentials:
        return False

    del credentials[issuer]

    final_value, is_encrypted = encrypt_oauth_credentials(credentials, service)
    if is_encrypted and isinstance(final_value, str):
        final_value = {"_cipher": final_value}

    row.config_value = final_value
    row.is_encrypted = is_encrypted
    flag_modified(row, "config_value")
    await db.commit()
    logger.info("Deleted OAuth credentials for issuer '%s'", issuer)
    return True
