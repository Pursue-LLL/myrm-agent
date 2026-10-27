"""Config encryption migration service.

Seals plaintext sensitive configs: the rows saved before their key was listed as sensitive, or before encryption was
available to the instance. Also moves the key of the user's own model endpoint, which an older build saved inside the
preferences, into the sealed row that holds it now.

[INPUT]
- app.database.connection::get_session
- app.services.config.encryption::get_encryption_service/is_sensitive_config
- app.services.config.service::extract_cipher (POS: cipher envelope reader)

[OUTPUT]
- seal_stored_configs: the startup sweep, one session for all migrations below
- migrate_configs_to_encrypted: async function to perform migration
- migrate_config_history_to_encrypted: seals the plaintext values the audit history kept of sensitive configs
- move_privacy_routing_key: moves ``personalSettings.privacyRouting.localApiKey`` into the ``privacyRoutingSecret`` row

[POS]
Idempotent migration logic. Runs on server startup, in every mode (local, desktop and sandbox), to transparently
upgrade existing plaintext configs to encrypted format; a mode that does not encrypt configs has nothing to seal.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.config.encryption import get_encryption_service, is_sensitive_config
from app.services.config.service import _create_initial_version, _increment_version, extract_cipher

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.config.encryption import ConfigEncryptionService

logger = logging.getLogger(__name__)

_PERSONAL_SETTINGS = "personalSettings"
_PRIVACY_ROUTING = "privacyRouting"
_PRIVACY_ROUTING_SECRET = "privacyRoutingSecret"
_LEGACY_KEY_FIELD = "localApiKey"
_MIGRATION_DEVICE_ID = "server-migration"


async def seal_stored_configs() -> None:
    """Seal every stored secret, and the history that repeats it, that was saved in plaintext.

    A sandbox seals new writes with the key its control plane provides, so the rows it saved earlier need this sweep as
    much as a local instance does. A mode that does not encrypt configs finds nothing to seal.
    """
    from app.database.connection import get_session

    async with get_session() as db:
        stats = await migrate_configs_to_encrypted(db)
        if stats["migrated"] > 0:
            logger.info("[Startup] Config encryption migration complete: %s", stats)
        else:
            logger.debug("[Startup] No configs to migrate: %s", stats)
        await migrate_config_history_to_encrypted(db)
        if await move_privacy_routing_key(db):
            logger.info("[Startup] Moved the local model key out of the preferences into its sealed row")


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

        # A sealed row is the bare ciphertext or the ``{"_cipher": ...}`` envelope the config service writes; sealing
        # either again would bury the value under a second layer.
        if extract_cipher(config.config_value) is not None:
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
    if not isinstance(value, dict) or extract_cipher(value) is not None:
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


def _split_legacy_key(snapshot: object) -> tuple[dict[str, object], object] | None:
    """A ``personalSettings`` value without ``privacyRouting.localApiKey`` and the key it held; None when it has no such field."""
    if not isinstance(snapshot, dict):
        return None
    routing = snapshot.get(_PRIVACY_ROUTING)
    if not isinstance(routing, dict) or _LEGACY_KEY_FIELD not in routing:
        return None
    kept_routing = {name: item for name, item in routing.items() if name != _LEGACY_KEY_FIELD}
    return {**snapshot, _PRIVACY_ROUTING: kept_routing}, routing[_LEGACY_KEY_FIELD]


def _add_privacy_routing_secret_row(db: "AsyncSession", local_api_key: str) -> None:
    """Add the sealed ``privacyRoutingSecret`` row and its first history entry, written the way ``ConfigService.set`` does."""
    import uuid

    from app.database.models import ConfigAuditLog, UserConfig

    value: dict[str, object] = {_LEGACY_KEY_FIELD: local_api_key}
    stored, encrypted = get_encryption_service().encrypt_if_needed(_PRIVACY_ROUTING_SECRET, value)
    db_value: dict[str, object] = {"_cipher": stored} if isinstance(stored, str) and encrypted else value
    version = _create_initial_version()
    db.add(
        UserConfig(
            id=str(uuid.uuid4()),
            config_key=_PRIVACY_ROUTING_SECRET,
            config_value=db_value,
            version=version,
            last_device_id=_MIGRATION_DEVICE_ID,
            is_encrypted=encrypted,
        )
    )
    db.add(
        ConfigAuditLog(
            id=str(uuid.uuid4()),
            config_key=_PRIVACY_ROUTING_SECRET,
            previous_value=None,
            new_value=db_value,
            version=version,
            device_id=_MIGRATION_DEVICE_ID,
        )
    )


async def move_privacy_routing_key(db: "AsyncSession") -> bool:
    """Move the local model key from the preferences into its own sealed row; returns whether anything was changed.

    An older build saved the key as ``personalSettings.privacyRouting.localApiKey``: a plain row, so the key sat in
    plaintext on disk and in an instance archive, and every snapshot in the audit history repeated each key ever saved.
    The key found in the current preferences is carried into the ``privacyRoutingSecret`` row, unless that row already
    exists (it was written after the key, so it wins). The field is then removed from the preferences, which get a new
    version so a client that still holds the old value resolves a conflict instead of writing the key back, and from every
    snapshot. All of it is one transaction: a failure changes nothing, and a second run finds nothing to move.
    """
    from sqlalchemy import String, cast, or_, select

    from app.database.models import ConfigAuditLog, UserConfig

    changed = False
    preferences = (await db.execute(select(UserConfig).where(UserConfig.config_key == _PERSONAL_SETTINGS))).scalar_one_or_none()
    if preferences is not None and not preferences.is_encrypted:
        split = _split_legacy_key(preferences.config_value)
        if split is not None:
            without_key, legacy_key = split
            secret_exists = (
                await db.execute(select(UserConfig.id).where(UserConfig.config_key == _PRIVACY_ROUTING_SECRET))
            ).first() is not None
            if isinstance(legacy_key, str) and legacy_key and not secret_exists:
                _add_privacy_routing_secret_row(db, legacy_key)
            preferences.config_value = without_key
            preferences.version = _increment_version(preferences.version)
            preferences.last_device_id = _MIGRATION_DEVICE_ID
            changed = True

    snapshots = (
        (
            await db.execute(
                select(ConfigAuditLog).where(
                    ConfigAuditLog.config_key == _PERSONAL_SETTINGS,
                    or_(
                        cast(ConfigAuditLog.previous_value, String).contains(_LEGACY_KEY_FIELD),
                        cast(ConfigAuditLog.new_value, String).contains(_LEGACY_KEY_FIELD),
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    for snapshot in snapshots:
        previous = _split_legacy_key(snapshot.previous_value)
        current = _split_legacy_key(snapshot.new_value)
        if previous is not None:
            snapshot.previous_value = previous[0]
            changed = True
        if current is not None:
            snapshot.new_value = current[0]
            changed = True

    if changed:
        await db.commit()
    return changed
