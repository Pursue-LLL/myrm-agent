"""[INPUT]
- app.core.channel_bridge.config_cache::invalidate_user_configs_cache (POS: Business-layer config caching. Simple dict + timestamp implementation.)
- app.core.infra.ingress_requirement::invalidate_ingress_requirement_cache (POS: Server-side single source of truth for System settings and channel Ingress badges.)
- app.schemas.config::ConfigKey / ConfigRecord / ConfigSetRequest / ConfigSyncRequest / ConfigSyncResponse / ConflictErrorResponse (POS: 配置 API 数据模型)
- app.services.channels::credential_reload (POS: Channel bridge business services.)
- app.services.config.service::VersionConflictError / config_service (POS: 配置服务)
- app.services.integrations.search_verify::invalidate_search_verify_cache (POS: Settings/API search provider verify endpoint and readiness gate backing service.)
- app.api.config.routes.support::_VALID_CONFIG_KEYS / _hot_reload_browser_proxy / _hot_reload_cloud_browser / _validate_config_value (POS: 配置 API 的域子模块；由 app/api/config/router.py 按原顺序挂载。)

[OUTPUT]
- get_config: 获取单个配置
- set_config: 设置配置（带乐观锁）
- get_config_history: 获取配置历史记录 (Configuration Time-Machine)
- rollback_config: 回滚配置到指定版本 (Configuration Time-Machine)
- delete_config: 删除配置
- sync_configs: 批量同步配置

[POS]
配置 API 的域子模块；由 app/api/config/router.py 按原顺序挂载。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
from app.core.infra.ingress_requirement import invalidate_ingress_requirement_cache
from app.schemas.config import (
    ConfigKey,
    ConfigRecord,
    ConfigSetRequest,
    ConfigSyncRequest,
    ConfigSyncResponse,
    ConflictErrorResponse,
)
from app.services.channels import credential_reload
from app.services.config.service import VersionConflictError, config_service
from app.services.integrations.search_verify import invalidate_search_verify_cache

from .support import (
    _VALID_CONFIG_KEYS,
    _hot_reload_browser_proxy,
    _hot_reload_cloud_browser,
    _validate_config_value,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{config_key}", response_model=ConfigRecord)
async def get_config(
    config_key: ConfigKey,
) -> ConfigRecord:
    """获取单个配置"""
    try:
        record = await config_service.get(config_key)
        if record is None:
            return ConfigRecord(
                key=config_key,
                value={},
                version="0",
                updatedAt="",
                deviceId="",
            )
        return record
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get config '%s': %s", config_key, e)
        raise HTTPException(status_code=500, detail="Failed to get config") from e


@router.put(
    "/{config_key}",
    response_model=ConfigRecord,
    responses={409: {"model": ConflictErrorResponse}},
)
async def set_config(
    config_key: ConfigKey,
    request: ConfigSetRequest,
) -> ConfigRecord:
    """设置配置（带乐观锁）

    如果提供了 expectedVersion 且与服务端版本不匹配，返回 409 冲突。
    """
    try:
        request.value = _validate_config_value(config_key, request.value, operation="set")

        record = await config_service.set(
            config_key=config_key,
            value=request.value,
            expected_version=request.expected_version,
            device_id=request.device_id,
        )
        invalidate_user_configs_cache()
        invalidate_search_verify_cache()
        invalidate_ingress_requirement_cache()
        if config_key == "providers":
            try:
                from app.core.skills.gates.x_live_search_skill_enable import maybe_enable_x_live_search_skill

                providers_value = request.value if isinstance(request.value, dict) else None
                await maybe_enable_x_live_search_skill(providers_value)
            except Exception as exc:
                logger.warning("x-live-search skill auto-enable skipped: %s", exc)
            from app.core.channel_bridge.config_cache import (
                await_memory_manager_config_invalidation,
            )

            await await_memory_manager_config_invalidation()
        if config_key == "channels":
            from app.core.channel_bridge.channel_policy import SqlChannelPolicyProvider
            from app.core.channel_bridge.setup import refresh_reaction_policy

            SqlChannelPolicyProvider._invalidate_cache()
            await refresh_reaction_policy()
        if config_key.endswith("Credentials"):
            await credential_reload.reload_channel_credentials(config_key)
        if config_key == "browserCloudProvider":
            await _hot_reload_cloud_browser(request.value)
        if config_key == "browserProxy":
            await _hot_reload_browser_proxy(request.value)
        if config_key == "personalSettings" and isinstance(request.value, dict):
            from app.core.infra.tls_config import sync_tls_env_from_config

            sync_tls_env_from_config(request.value)
        return record
    except VersionConflictError as e:
        raise HTTPException(
            status_code=409,
            detail={"detail": "Version conflict", "serverVersion": e.server_version},
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to set config '%s': %s", config_key, e)
        raise HTTPException(status_code=500, detail="Failed to set config") from e


@router.get("/{config_key}/history")
async def get_config_history(config_key: str, limit: int = Query(50, ge=1, le=100)) -> list[dict[str, object]]:
    """获取配置历史记录 (Configuration Time-Machine)"""
    if config_key not in _VALID_CONFIG_KEYS:
        raise HTTPException(status_code=400, detail=f"Invalid config key: {config_key}")

    try:
        return await config_service.get_history(config_key, limit=limit)
    except Exception as e:
        logger.error(f"Failed to get history for config '{config_key}': {e}")
        raise HTTPException(status_code=500, detail="Failed to get config history") from e


@router.post("/{config_key}/rollback/{version}", response_model=ConfigRecord)
async def rollback_config(config_key: str, version: str, device_id: str = Query(..., description="设备ID")) -> ConfigRecord:
    """回滚配置到指定版本 (Configuration Time-Machine)"""
    if config_key not in _VALID_CONFIG_KEYS:
        raise HTTPException(status_code=400, detail=f"Invalid config key: {config_key}")

    try:
        # Get the old value from history
        from typing import cast

        from sqlalchemy import select

        from app.database.connection import get_session
        from app.database.models import ConfigAuditLog
        from app.services.config.service import _decrypt_audit_log_value

        async with get_session() as session:
            stmt = select(ConfigAuditLog).where(
                ConfigAuditLog.config_key == config_key,
                ConfigAuditLog.version == version,
            )
            result = await session.execute(stmt)
            log = result.scalar_one_or_none()

            if not log:
                raise HTTPException(status_code=404, detail=f"Audit log for version {version} not found")

            new_value = _decrypt_audit_log_value(config_key, cast(dict[str, object], log.new_value))
            if new_value is None:
                new_value = {}

        # Omni-Config validation for rollback
        # This ensures that rolling back to an older schema version will automatically
        # populate missing fields with their current default values, preventing schema corruption.
        new_value = _validate_config_value(config_key, new_value, operation="rollback")

        # Use the standard set method to save the validated rollback state
        record = await config_service.set(
            config_key=config_key,
            value=new_value,
            device_id=device_id,
        )

        # Invalidate caches
        invalidate_user_configs_cache()
        invalidate_ingress_requirement_cache()
        if config_key == "providers":
            try:
                from app.core.skills.gates.x_live_search_skill_enable import maybe_enable_x_live_search_skill

                providers_value = new_value if isinstance(new_value, dict) else None
                await maybe_enable_x_live_search_skill(providers_value)
            except Exception as exc:
                logger.warning("x-live-search skill auto-enable skipped on rollback: %s", exc)
            from app.core.channel_bridge.config_cache import (
                await_memory_manager_config_invalidation,
            )

            await await_memory_manager_config_invalidation()
        if config_key == "searchServices":
            invalidate_search_verify_cache()

        return record
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rollback config '{config_key}' to version {version}: {e}")
        raise HTTPException(status_code=500, detail="Failed to rollback config") from e


@router.delete("/{config_key}")
async def delete_config(
    config_key: ConfigKey,
) -> dict[str, bool]:
    """删除配置"""
    try:
        deleted = await config_service.delete(config_key)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Config '{config_key}' not found")
        invalidate_user_configs_cache()
        invalidate_search_verify_cache()
        invalidate_ingress_requirement_cache()
        if config_key == "channels":
            from app.core.channel_bridge.channel_policy import SqlChannelPolicyProvider
            from app.core.channel_bridge.setup import refresh_reaction_policy

            SqlChannelPolicyProvider._invalidate_cache()
            await refresh_reaction_policy()
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete config '%s': %s", config_key, e)
        raise HTTPException(status_code=500, detail="Failed to delete config") from e


@router.post("/sync", response_model=ConfigSyncResponse)
async def sync_configs(
    request: ConfigSyncRequest,
) -> ConfigSyncResponse:
    """批量同步配置

    支持多个配置的原子性同步，返回冲突列表和新版本号。
    """
    try:
        changes = []
        validation_errors: list[dict[str, str]] = []
        for change in request.changes:
            try:
                validated_value = _validate_config_value(
                    change.key,
                    change.value,
                    operation="sync",
                )
            except HTTPException as exc:
                validation_errors.append({"key": change.key, "message": str(exc.detail)})
                continue
            changes.append(change.model_copy(update={"value": validated_value}))

        if validation_errors:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Configuration sync validation failed",
                    "validation_errors": validation_errors,
                },
            )

        result = await config_service.sync(
            changes=changes,
            device_id=request.device_id,
        )
        if result.new_versions:
            invalidate_user_configs_cache()
            invalidate_search_verify_cache()
            invalidate_ingress_requirement_cache()
            if "channels" in result.new_versions:
                from app.core.channel_bridge.channel_policy import (
                    SqlChannelPolicyProvider,
                )
                from app.core.channel_bridge.setup import refresh_reaction_policy

                SqlChannelPolicyProvider._invalidate_cache()
                await refresh_reaction_policy()
            if "browserCloudProvider" in result.new_versions:
                browser_change = next((c for c in changes if c.key == "browserCloudProvider"), None)
                if browser_change:
                    await _hot_reload_cloud_browser(browser_change.value)
            if "browserProxy" in result.new_versions:
                proxy_change = next((c for c in changes if c.key == "browserProxy"), None)
                if proxy_change:
                    await _hot_reload_browser_proxy(proxy_change.value)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to sync configs: %s", e)
        raise HTTPException(status_code=500, detail="Failed to sync configs") from e
