"""配置服务

管理用户配置的存储和同步。
支持版本控制（乐观锁）和批量同步。
敏感配置在 Sandbox 模式下自动服务端加密。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult

from app.database.models import ConfigAuditLog, UserConfig
from app.platform_utils import get_session_factory
from app.schemas.config import ConfigChange, ConfigKey, ConfigRecord, ConfigSyncResponse
from app.services.config.encryption import get_encryption_service

if TYPE_CHECKING:
    from app.services.config.encryption import ConfigEncryptionService

SYSTEM_CONFIG_USER_ID = "__system__"  # reserved for future system-default config flows

logger = logging.getLogger(__name__)


class VersionConflictError(Exception):
    """版本冲突错误"""

    def __init__(self, key: str, expected_version: str, server_version: str):
        self.key = key
        self.expected_version = expected_version
        self.server_version = server_version
        super().__init__(f"Version conflict for key '{key}': expected={expected_version}, server={server_version}")


def _create_initial_version() -> str:
    return f"{int(datetime.now().timestamp() * 1000)}_0"


def _config_values_equal(a: dict[str, object], b: dict[str, object]) -> bool:
    import json

    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def _increment_version(current: str) -> str:
    now = int(datetime.now().timestamp() * 1000)
    parts = current.split("_")
    if len(parts) != 2:
        return f"{now}_0"

    timestamp, counter = int(parts[0]), int(parts[1])
    if timestamp == now:
        return f"{now}_{counter + 1}"
    return f"{now}_0"


def _encrypt_if_sensitive(key: str, value: dict[str, object]) -> tuple[dict[str, object] | str, bool]:
    """Encrypt the value if the key is sensitive. Returns (stored_value, is_encrypted).

    Guards against double-encryption: if value is already a cipher envelope, skip.
    """
    if "_cipher" in value and len(value) == 1 and isinstance(value.get("_cipher"), str):
        logger.warning("Config '%s': value is already a cipher envelope, skipping encryption", key)
        return value, True
    service = get_encryption_service()
    return service.encrypt_if_needed(key, value)


def _decrypt_if_needed(config: UserConfig) -> dict[str, object]:
    """Decrypt the config value if it was encrypted at rest.

    Handles:
    - Normal decryption with current key
    - Double-encrypted data (legacy bug workaround)
    - Legacy device-fingerprint-encrypted data (transparent migration)
    """
    if not config.is_encrypted:
        raw_value = config.config_value
        if isinstance(raw_value, dict):
            return {str(k): v for k, v in raw_value.items()}
        return {}

    service = get_encryption_service()
    raw = config.config_value
    cipher = _extract_cipher(raw)
    if cipher is None:
        logger.warning("Config '%s' marked encrypted but no cipher found, returning as-is", config.config_key)
        return {str(k): v for k, v in raw.items()} if isinstance(raw, dict) else {}

    decrypted = _try_decrypt(cipher, service, config.config_key)
    if decrypted is None:
        return {}

    if isinstance(decrypted, dict) and "_cipher" in decrypted and len(decrypted) == 1:
        inner = decrypted["_cipher"]
        if isinstance(inner, str):
            logger.warning("Config '%s' was double-encrypted, performing second decryption", config.config_key)
            decrypted = _try_decrypt(inner, service, config.config_key)
            if decrypted is None:
                return {}

    return decrypted  # type: ignore[return-value]


def _extract_cipher(raw: object) -> str | None:
    """Extract cipher string from raw config value."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        cipher = raw.get("_cipher")
        return cipher if isinstance(cipher, str) else None
    return None


def _try_decrypt(
    cipher: str,
    service: "ConfigEncryptionService",
    config_key: str,
) -> dict[str, object] | None:
    """Try to decrypt with current key, falling back to legacy fingerprint key."""
    from myrm_agent_harness.utils.crypto import DecryptionError

    try:
        return service.decrypt(cipher)
    except DecryptionError:
        pass

    legacy_result = _try_legacy_fingerprint_decrypt(cipher, config_key)
    if legacy_result is not None:
        return legacy_result

    logger.error("Config '%s': decryption failed with both current and legacy keys", config_key)
    return None


def _try_legacy_fingerprint_decrypt(cipher: str, config_key: str) -> dict[str, object] | None:
    """Attempt decryption with legacy device-fingerprint-derived key for migration."""
    from myrm_agent_harness.utils import derive_key_from_fingerprint, get_device_fingerprint
    from myrm_agent_harness.utils.crypto import ConfigCrypto, DecryptionError

    try:
        fp = get_device_fingerprint()
        legacy_key = derive_key_from_fingerprint(fp)
        result = ConfigCrypto.decrypt_value(cipher, legacy_key)
        logger.warning(
            "Config '%s': decrypted with legacy fingerprint key. Re-save this config to migrate to new encryption key.",
            config_key,
        )
        return result
    except (DecryptionError, Exception):
        return None


def _decrypt_audit_log_value(config_key: str, value: dict[str, object] | None) -> dict[str, object] | None:
    """Decrypt audit log value if it is encrypted."""
    if value is None:
        return None
    cipher = _extract_cipher(value)
    if cipher is None:
        return {str(k): v for k, v in value.items()}
    service = get_encryption_service()
    decrypted = _try_decrypt(cipher, service, config_key)
    return decrypted if decrypted is not None else {}


def _build_config_record(config: UserConfig, value: dict[str, object], *, is_system_default: bool = False) -> ConfigRecord:
    """Build ConfigRecord from UserConfig model."""
    return ConfigRecord(
        key=cast(ConfigKey, config.config_key),
        value=value,
        version=config.version,
        updatedAt=config.updated_at.isoformat(),
        deviceId=config.last_device_id,
        encrypted=config.is_encrypted,
        isSystemDefault=is_system_default,
    )


class ConfigService:
    """配置服务

    提供配置的 CRUD 操作，支持：
    - 版本控制（乐观锁）
    - 批量同步
    - 冲突检测
    - 敏感配置自动服务端加密/解密
    """

    async def get_all(self, keys: list[str] | None = None) -> dict[str, ConfigRecord]:
        """获取所有配置"""
        if keys is not None and len(keys) == 0:
            return {}

        output: dict[str, ConfigRecord] = {}

        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(UserConfig)
            if keys:
                stmt = stmt.where(UserConfig.config_key.in_(keys))
            result = await session.execute(stmt)

            for config in result.scalars().all():
                try:
                    value = _decrypt_if_needed(config)
                    output[config.config_key] = _build_config_record(config, value)
                except Exception as e:
                    logger.warning("Failed to process config '%s': %s, skipping", config.config_key, str(e))

        return output

    async def get(self, config_key: str) -> ConfigRecord | None:
        """获取配置"""
        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await session.execute(select(UserConfig).where(UserConfig.config_key == config_key))
            config = result.scalar_one_or_none()

            if config:
                value = _decrypt_if_needed(config)
                return _build_config_record(config, value)

            return None

    async def set(
        self,
        config_key: str,
        value: dict[str, object],
        device_id: str,
        expected_version: str | None = None,
    ) -> ConfigRecord:
        """设置配置（带乐观锁）

        敏感配置自动服务端加密，调用方无需关心加密细节。
        """
        stored_value, encrypted = _encrypt_if_sensitive(config_key, value)
        db_value: dict[str, object] = {"_cipher": stored_value} if isinstance(stored_value, str) and encrypted else value

        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await session.execute(select(UserConfig).where(UserConfig.config_key == config_key))
            existing = result.scalar_one_or_none()

            if existing:
                if expected_version and existing.version != expected_version:
                    current_value = _decrypt_if_needed(existing)
                    if _config_values_equal(current_value, value):
                        logger.info(
                            "Idempotent config sync for '%s': version mismatch but content identical",
                            config_key,
                        )
                        return _build_config_record(existing, current_value)
                    raise VersionConflictError(config_key, expected_version, existing.version)

                previous_db_value = existing.config_value

                existing.config_value = db_value
                existing.version = _increment_version(existing.version)
                existing.last_device_id = device_id
                existing.is_encrypted = encrypted
                existing.updated_at = datetime.now()

                audit_log = ConfigAuditLog(
                    id=str(uuid.uuid4()),
                    config_key=config_key,
                    previous_value=previous_db_value,
                    new_value=db_value,
                    version=existing.version,
                    device_id=device_id,
                    created_at=datetime.now(),
                )
                session.add(audit_log)

                await session.commit()
                await session.refresh(existing)

                logger.warning("Updated config '%s', version=%s", config_key, existing.version)
                return _build_config_record(existing, value)
            else:
                new_version = _create_initial_version()
                new_config = UserConfig(
                    id=str(uuid.uuid4()),
                    config_key=config_key,
                    config_value=db_value,
                    version=new_version,
                    last_device_id=device_id,
                    is_encrypted=encrypted,
                )
                session.add(new_config)

                audit_log = ConfigAuditLog(
                    id=str(uuid.uuid4()),
                    config_key=config_key,
                    previous_value=None,
                    new_value=db_value,
                    version=new_version,
                    device_id=device_id,
                    created_at=datetime.now(),
                )
                session.add(audit_log)

                await session.commit()
                await session.refresh(new_config)

                logger.warning("Created config '%s', version=%s", config_key, new_version)
                return _build_config_record(new_config, value)

    async def delete(self, config_key: str) -> bool:
        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await session.execute(delete(UserConfig).where(UserConfig.config_key == config_key))
            await session.commit()

            deleted = False
            if isinstance(result, CursorResult):
                deleted = (result.rowcount or 0) > 0
            if deleted:
                logger.warning("Deleted config '%s'", config_key)

            return deleted

    async def sync(
        self,
        changes: list[ConfigChange],
        device_id: str,
    ) -> ConfigSyncResponse:
        conflicts: list[ConfigKey] = []
        new_versions: dict[str, str] = {}

        for change in changes:
            try:
                record = await self.set(
                    config_key=change.key,
                    value=change.value,
                    device_id=device_id,
                    expected_version=change.expected_version,
                )
                new_versions[change.key] = record.version
            except VersionConflictError:
                conflicts.append(change.key)

        return ConfigSyncResponse(
            success=len(conflicts) == 0,
            conflicts=conflicts,
            newVersions=new_versions,
        )

    async def get_history(self, config_key: str, limit: int = 50) -> list[dict[str, object]]:
        """获取配置历史记录"""
        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = (
                select(ConfigAuditLog)
                .where(ConfigAuditLog.config_key == config_key)
                .order_by(ConfigAuditLog.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            logs = result.scalars().all()

            return [
                {
                    "id": log.id,
                    "version": log.version,
                    "previous_value": _decrypt_audit_log_value(config_key, cast(dict[str, object] | None, log.previous_value)),
                    "new_value": _decrypt_audit_log_value(config_key, cast(dict[str, object], log.new_value)),
                    "device_id": log.device_id,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in logs
            ]


config_service = ConfigService()
