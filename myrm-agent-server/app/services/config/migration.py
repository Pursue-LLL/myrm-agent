"""Config encryption migration service.

Automatically migrates plaintext sensitive configs to encrypted format when
Local mode encryption is first enabled.

[INPUT]
- app.database.connection::get_session
- app.services.config_encryption_service::get_encryption_service

[OUTPUT]
- migrate_configs_to_encrypted: async function to perform migration
- migrate_config_history_to_encrypted: seals the plaintext values the audit history kept of sensitive configs

[POS]
One-time migration logic. Runs on server startup to transparently upgrade
existing plaintext configs to encrypted format.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.config.encryption import get_encryption_service, is_sensitive_config
from app.services.config.service import _extract_cipher

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.config.encryption import ConfigEncryptionService

logger = logging.getLogger(__name__)


async def migrate_configs_to_encrypted(db: "AsyncSession") -> dict[str, int]:
    """Migrate plaintext sensitive configs to encrypted format.

    Scans all user_configs for sensitive keys stored as plaintext (dict),
    encrypts them, and updates the database.

    Args:
        db: Database session

    Returns:
        Migration statistics: {"migrated": count, "skipped": count, "errors": count}
    """
    from sqlalchemy import select

    from app.database.models import UserConfig

    encryption_service = get_encryption_service()

    result = await db.execute(select(UserConfig))
    configs = result.scalars().all()

    stats = {"migrated": 0, "skipped": 0, "errors": 0}

    for config in configs:
        if not is_sensitive_config(config.config_key):
            stats["skipped"] += 1
            continue

        if isinstance(config.config_value, str):
            stats["skipped"] += 1
            continue

        if not isinstance(config.config_value, dict):
            logger.warning(f"Unexpected config_value type for {config.config_key}: {type(config.config_value)}")
            stats["errors"] += 1
            continue

        try:
            encrypted_value, is_encrypted = encryption_service.encrypt_if_needed(config.config_key, config.config_value)

            if not is_encrypted:
                stats["skipped"] += 1
                continue

            config.config_value = encrypted_value  # type: ignore
            # Reads go by this flag, not by the shape of the value: without it the ciphertext is returned as {}.
            config.is_encrypted = True
            stats["migrated"] += 1

            logger.info(f"Migrated config to encrypted: config_key={config.config_key}, version={config.version}")

        except Exception as e:
            logger.error(f"Failed to migrate config {config.id}: {e}")
            stats["errors"] += 1

    if stats["migrated"] > 0:
        await db.commit()
        logger.info(f"Config encryption migration complete: {stats}")
    else:
        logger.debug(f"No configs to migrate: {stats}")

    return stats


def _sealed_history_value(
    encryption_service: ConfigEncryptionService, config_key: str, value: object
) -> dict[str, object] | None:
    """The cipher envelope for a plaintext history value; None when there is nothing to seal."""
    if not isinstance(value, dict) or _extract_cipher(value) is not None:
        return None
    ciphertext, is_encrypted = encryption_service.encrypt_if_needed(config_key, {str(k): v for k, v in value.items()})
    return {"_cipher": ciphertext} if is_encrypted else None


async def migrate_config_history_to_encrypted(db: "AsyncSession") -> int:
    """Seal the plaintext values the audit history kept of sensitive configs; returns how many values were sealed.

    The audit log repeats every value a config row ever had, so a row saved before its key became sensitive still sits in
    plaintext there. Values that are already sealed and the history of keys that are not secret stay as they are, which
    makes a second run a no-op.
    """
    from sqlalchemy import select

    from app.database.models import ConfigAuditLog

    encryption_service = get_encryption_service()
    keys = (await db.execute(select(ConfigAuditLog.config_key).distinct())).scalars().all()
    sensitive_keys = [key for key in keys if encryption_service.should_encrypt(key)]
    if not sensitive_keys:
        return 0

    rows = (await db.execute(select(ConfigAuditLog).where(ConfigAuditLog.config_key.in_(sensitive_keys)))).scalars().all()
    sealed = 0
    for row in rows:
        previous = _sealed_history_value(encryption_service, row.config_key, row.previous_value)
        if previous is not None:
            row.previous_value = previous
            sealed += 1
        current = _sealed_history_value(encryption_service, row.config_key, row.new_value)
        if current is not None:
            row.new_value = current
            sealed += 1

    if sealed:
        await db.commit()
        logger.info("Sealed %d plaintext config history values", sealed)
    return sealed


async def migrate_configs_with_recovery_key(db: "AsyncSession", recovery_key: bytes) -> dict[str, int]:
    """Migrate configs encrypted with an old key to the current device key.

    Used when a user imports a recovery key after a hardware change.
    Attempts to decrypt all sensitive configs with the recovery key,
    and if successful, re-encrypts them with the current encryption service.

    Args:
        db: Database session
        recovery_key: The old 32-byte AES key to use for decryption

    Returns:
        Migration statistics: {"migrated": count, "skipped": count, "failed": count}
    """
    from myrm_agent_harness.utils.crypto.config_crypto import ConfigCrypto
    from sqlalchemy import select

    from app.database.models import UserConfig

    encryption_service = get_encryption_service()
    if not encryption_service.has_key:
        raise RuntimeError("Current encryption service has no key. Cannot re-encrypt.")

    result = await db.execute(select(UserConfig))
    configs = result.scalars().all()

    stats = {"migrated": 0, "skipped": 0, "failed": 0}

    for config in configs:
        if not is_sensitive_config(config.config_key):
            stats["skipped"] += 1
            continue

        if not isinstance(config.config_value, str):
            # It's plaintext (dict), no need to recover
            stats["skipped"] += 1
            continue

        # Try to decrypt with current key first to see if it's already migrated
        try:
            ConfigCrypto.decrypt_value(config.config_value, encryption_service.raw_key)
            # If it succeeds, it's already encrypted with the current key
            stats["skipped"] += 1
            continue
        except Exception:
            pass  # Failed to decrypt with current key, which means we need to try recovery key

        # Try to decrypt with recovery key
        try:
            decrypted_dict = ConfigCrypto.decrypt_value(config.config_value, recovery_key)

            # Re-encrypt with current key
            encrypted_value, is_encrypted = encryption_service.encrypt_if_needed(config.config_key, decrypted_dict)

            if is_encrypted:
                config.config_value = encrypted_value

                stats["migrated"] += 1
                logger.info(f"Recovered and re-encrypted config: config_key={config.config_key}")
            else:
                stats["failed"] += 1
        except Exception as e:
            logger.warning(f"Failed to recover config {config.id} with provided key: {e}")
            stats["failed"] += 1

    if stats["migrated"] > 0:
        await db.commit()
        logger.info(f"Recovery key migration complete: {stats}")

    return stats


async def validate_recovery_key(db: "AsyncSession", recovery_key: bytes) -> dict[str, int]:
    """Validate a recovery key without performing migration.

    Attempts to decrypt all sensitive configs with the recovery key
    and counts how many would be successfully recovered.

    Args:
        db: Database session
        recovery_key: The old 32-byte AES key to use for decryption

    Returns:
        Validation statistics: {"recoverable": count, "skipped": count, "failed": count}
    """
    from myrm_agent_harness.utils.crypto.config_crypto import ConfigCrypto
    from sqlalchemy import select

    from app.database.models import UserConfig

    encryption_service = get_encryption_service()

    result = await db.execute(select(UserConfig))
    configs = result.scalars().all()

    stats = {"recoverable": 0, "skipped": 0, "failed": 0}

    for config in configs:
        if not is_sensitive_config(config.config_key):
            stats["skipped"] += 1
            continue

        if not isinstance(config.config_value, str):
            # It's plaintext (dict), no need to recover
            stats["skipped"] += 1
            continue

        # Try to decrypt with current key first to see if it's already migrated
        if encryption_service.has_key:
            try:
                ConfigCrypto.decrypt_value(config.config_value, encryption_service.raw_key)
                # If it succeeds, it's already encrypted with the current key
                stats["skipped"] += 1
                continue
            except Exception:
                pass  # Failed to decrypt with current key, which means we need to try recovery key

        # Try to decrypt with recovery key
        try:
            ConfigCrypto.decrypt_value(config.config_value, recovery_key)
            stats["recoverable"] += 1
        except Exception:
            stats["failed"] += 1

    return stats
