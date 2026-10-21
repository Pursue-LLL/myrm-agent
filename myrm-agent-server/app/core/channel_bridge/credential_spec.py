"""Business-layer credential source — DB-backed credential loading.

Provides the ``CredentialSource`` callback for the framework's
``resolve_credentials`` and ``create_channels`` functions. Also exposes
``is_channel_enabled`` for checking channel enablement in DB.

Sensitive credentials (identified by ``is_sensitive_config``) are stored
encrypted at rest. This module transparently decrypts them before
returning to callers.

[INPUT]
- app.database.models::UserConfig (POS: DB credential storage)
- app.database.connection::get_session (POS: async DB session factory)
- app.middleware.auth::get_local_admin_user_id (POS: local admin user resolution)
- app.core.security.config_crypto::decrypt_config_value (POS: credential decryption)

[OUTPUT]
- load_from_db: credential dict loader with transparent decryption (CredentialSource callback)
- is_channel_enabled: check if a channel is enabled in DB

[POS]
Business-layer credential source. Bridges the framework's generic
credential resolution with the application's DB-backed storage.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def load_from_db(config_key: str) -> dict[str, object] | None:
    """Load credential dict from UserConfig DB, decrypting if needed.

    This function matches the ``CredentialSource`` signature from the
    framework layer and can be passed directly to ``resolve_credentials``
    or ``create_channels``.

    Returns ``None`` on any failure (missing user, no DB record, import error).
    """
    try:
        from sqlalchemy import select

        from app.database.connection import get_session
        from app.database.models import UserConfig

        async with get_session() as session:
            result = await session.execute(
                select(UserConfig).where(
                    UserConfig.config_key == config_key,
                )
            )
            config = result.scalar_one_or_none()

        if config is None:
            return None

        from app.services.config.encryption import get_encryption_service

        raw = config.config_value

        if config.is_encrypted:
            try:
                service = get_encryption_service()
            except Exception as exc:
                logger.error("%s: failed to get encryption service: %s", config_key, exc)
                return None
            if isinstance(raw, str):
                return service.decrypt(raw)
            if isinstance(raw, dict):
                cipher = raw.get("_cipher")
                if isinstance(cipher, str):
                    try:
                        return service.decrypt(cipher)
                    except Exception as exc:
                        logger.error("%s: decrypt failed: %s", config_key, exc)
                        return None
            logger.warning(
                "%s marked encrypted but value is not a cipher string, returning as-is",
                config_key,
            )

        if isinstance(raw, dict):
            # Unwrap {"_cipher": ...} left by ConfigService (is_encrypted should be True)
            cipher = raw.get("_cipher")
            if isinstance(cipher, str):
                service = get_encryption_service()
                try:
                    return service.decrypt(cipher)
                except Exception:
                    logger.warning("%s has _cipher but decryption failed", config_key)
                    return None
            logger.debug("%s credentials loaded from DB", config_key)
            return raw

        # Fallback: is_encrypted=False but value is a str (legacy encrypted data)
        if isinstance(raw, str) and raw:
            from app.services.config.encryption import is_sensitive_config

            if is_sensitive_config(config_key):
                service = get_encryption_service()
                try:
                    return service.decrypt(raw)
                except Exception:
                    logger.warning(
                        "%s: is_encrypted=False but value is non-dict str; decryption failed",
                        config_key,
                    )
            return None

        return None
    except Exception:
        return None


async def is_channel_enabled(config_key: str) -> bool:
    """Check whether a configured channel is enabled."""
    db_creds = await load_from_db(config_key)
    if db_creds is None:
        return False
    return db_creds.get("enabled", True) is not False
