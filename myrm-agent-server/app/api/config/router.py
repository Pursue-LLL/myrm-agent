"""配置管理 API 路由

[INPUT] app.services.config::config_service (POS: 配置核心业务逻辑服务)
[INPUT] app.schemas.config::OMNI_CONFIG_MODELS (POS: 配置服务 API 数据模型层)
[OUTPUT] router: FastAPI APIRouter 实例，包含配置相关的 HTTP 接口
[POS] 配置服务 API 路由层。处理 HTTP 请求，进行 Pre-flight Validation 强类型校验。

提供配置的 CRUD 操作，支持：
- 版本控制（乐观锁）
- 批量同步
- 敏感/非敏感配置分离
- 按需加载（keys 参数）

认证：
- 本地模式：使用固定的本地工作区身份
- Sandbox 模式：由 `SANDBOX_API_KEY` 中间件注入的单租户身份
"""

import logging
import time
from typing import get_args

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
from app.core.channel_bridge.config_parsers import invalidate_search_health_cache
from app.core.security.config_crypto import is_sensitive_config
from app.schemas.config import (
    OMNI_CONFIG_MODELS,
    AllConfigsResponse,
    ConfigKey,
    ConfigRecord,
    ConfigSetRequest,
    ConfigSyncRequest,
    ConfigSyncResponse,
    ConflictErrorResponse,
)
from app.services.config.service import VersionConflictError, config_service

logger = logging.getLogger(__name__)

router = APIRouter()

_VALID_CONFIG_KEYS: frozenset[str] = frozenset(get_args(ConfigKey))


def _validate_config_value(config_key: str, value: dict[str, object], *, operation: str) -> dict[str, object]:
    model_class = OMNI_CONFIG_MODELS.get(config_key)
    if not model_class:
        return value

    try:
        validated_data = model_class.model_validate(value)
    except Exception as exc:
        logger.warning("Omni-Config %s validation failed for %s: %s", operation, config_key, exc)
        raise HTTPException(
            status_code=422,
            detail=f"Configuration validation failed: {str(exc)}",
        ) from exc
    return validated_data.model_dump(exclude_unset=False)


@router.get("/schema/{key}", response_model=dict)
async def get_config_schema(key: str) -> dict[str, object]:
    """获取指定配置项的 JSON Schema"""
    if key not in _VALID_CONFIG_KEYS:
        raise HTTPException(status_code=400, detail=f"Invalid config key: {key}")

    model = OMNI_CONFIG_MODELS.get(key)
    if not model:
        raise HTTPException(
            status_code=404,
            detail=f"Schema not found for config key: {key}. This config has not been migrated to Omni-Config yet.",
        )

    return model.model_json_schema()


@router.get("", response_model=AllConfigsResponse)
async def get_all_configs(
    sensitive: bool | None = Query(None, description="过滤敏感/非敏感配置"),
    keys: str | None = Query(None, description="按需加载，逗号分隔的配置键，如 providers,chatSettings"),
) -> AllConfigsResponse:
    """获取配置

    Args:
        sensitive: 可选过滤器
            - None: 返回所有配置
            - True: 只返回敏感配置
            - False: 只返回非敏感配置
        keys: 可选，只返回指定键的配置，减少传输量
    """
    try:
        key_list: list[str] | None = None
        if keys:
            key_list = [k.strip() for k in keys.split(",") if k.strip()]
            invalid = [k for k in key_list if k not in _VALID_CONFIG_KEYS]
            if invalid:
                raise HTTPException(status_code=400, detail=f"Invalid config keys: {invalid}")

        all_configs = await config_service.get_all(keys=key_list)

        if sensitive is not None:
            filtered = {}
            for key, record in all_configs.items():
                if sensitive == is_sensitive_config(key):
                    filtered[key] = record
            return AllConfigsResponse(configs=filtered)

        return AllConfigsResponse(configs=all_configs)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get configs: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get configs") from e


@router.get("/readiness", response_model=dict)
async def get_config_readiness() -> dict[str, object]:
    """Check configuration readiness status.

    Returns configuration completeness status for each config type
    (provider, search, mcp, etc.) to help frontend guide user setup.

    Example response:
    {
        "provider": {
            "is_ready": false,
            "missing_items": ["api_key"],
            "suggestions": ["Add API key in Settings > Model Service"]
        },
        "search": {"is_ready": true},
        "onboarding_completed": false
    }
    """
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.channel_bridge.config_readiness import ProviderConfigChecker, SearchConfigChecker
    from app.database.connection import get_session
    from app.services.config.onboarding import check_onboarding_status

    try:
        user_configs = await load_user_configs()
    except Exception as exc:
        logger.warning("Failed to load user configs for readiness check: %s", exc)
        return {
            "provider": {
                "is_ready": False,
                "missing_items": ["config_load_failed"],
                "suggestions": ["Please try again or contact support"],
            },
            "search": {
                "is_ready": False,
                "missing_items": ["config_load_failed"],
                "suggestions": ["Please try again or contact support"],
            },
            "onboarding_completed": False,
        }

    provider_checker = ProviderConfigChecker()
    provider_result = provider_checker.check(user_configs.providers_dict)

    search_checker = SearchConfigChecker()
    if user_configs.search_is_user_configured:
        search_result = search_checker.check({"searchServiceConfigs": [{"enabled": True}]})
    else:
        search_result = search_checker.check(None)

    async with get_session() as db:
        onboarding_completed = await check_onboarding_status(db, "sandbox")

    return {
        "provider": provider_result.to_dict(),
        "search": search_result.to_dict(),
        "onboarding_completed": onboarding_completed,
    }


@router.post("/onboarding/complete")
async def complete_config_onboarding() -> dict[str, object]:
    """Mark user's first-time configuration as complete.

    Should be called after user successfully configures their first provider.
    """
    from app.database.connection import get_session
    from app.services.config.onboarding import complete_onboarding

    async with get_session() as db:
        success = await complete_onboarding(db, "sandbox")

    if not success:
        raise HTTPException(status_code=500, detail="Failed to complete onboarding")

    return {"success": True, "message": "Onboarding completed successfully"}


@router.get("/onboarding/recommendations")
async def get_onboarding_recommendations() -> dict[str, object]:
    """Get recommended provider configurations for new users.

    Returns a list of provider recommendations with setup instructions.
    """
    from app.services.config.onboarding import get_recommended_providers

    return {"providers": get_recommended_providers()}


def _require_local_deploy_mode() -> None:
    from app.config.deploy_mode import is_local_mode

    if not is_local_mode():
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SearXNG setup is only available in local deploy mode",
        )


@router.post("/onboarding/searxng/start")
async def start_local_searxng_endpoint() -> dict[str, object]:
    """Start SearXNG via Docker Compose and wait until HTTP probe succeeds (local/tauri only)."""
    _require_local_deploy_mode()
    from app.services.config.searxng_setup import start_local_searxng_and_wait

    return await start_local_searxng_and_wait()


@router.get("/onboarding/probe-local")
async def probe_local_models_endpoint() -> dict[str, object]:
    """Probe local model services and search backends for zero-config setup.

    Returns:
        results: Ollama / LM Studio probe results
        has_available: Whether at least one model service is available
        recommended_model: Best model to auto-select (if any)
        search: SearXNG probe results
        search_has_available: Whether SearXNG is reachable
        recommended_searxng_url: Default api_base when SearXNG is available
    """
    from app.core.channel_bridge.search_topology import get_default_searxng_api_base
    from app.services.config.onboarding import probe_local_models, probe_local_search

    results = await probe_local_models()
    search_results = await probe_local_search()

    available_results = [r for r in results if r.available]
    recommended_model: str | None = None

    if available_results:
        for result in available_results:
            if result.models:
                recommended_model = result.models[0].name
                break

    searxng_hit = next((s for s in search_results if s.get("provider") == "searxng" and s.get("available")), None)

    return {
        "results": [r.model_dump() for r in results],
        "has_available": len(available_results) > 0,
        "recommended_model": recommended_model,
        "search": search_results,
        "search_has_available": searxng_hit is not None,
        "recommended_searxng_url": (str(searxng_hit.get("base_url")) if searxng_hit else get_default_searxng_api_base()),
    }


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
        invalidate_search_health_cache()
        if config_key == "channels":
            from app.core.channel_bridge.channel_policy import SqlChannelPolicyProvider

            SqlChannelPolicyProvider._invalidate_cache()
        if config_key.endswith("Credentials"):
            await _try_hot_register_channel(config_key)
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
            stmt = select(ConfigAuditLog).where(ConfigAuditLog.config_key == config_key, ConfigAuditLog.version == version)
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
        if config_key == "searchServices":
            invalidate_search_health_cache()

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
        invalidate_search_health_cache()
        if config_key == "channels":
            from app.core.channel_bridge.channel_policy import SqlChannelPolicyProvider

            SqlChannelPolicyProvider._invalidate_cache()
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
            invalidate_search_health_cache()
            if "channels" in result.new_versions:
                from app.core.channel_bridge.channel_policy import SqlChannelPolicyProvider

                SqlChannelPolicyProvider._invalidate_cache()
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to sync configs: %s", e)
        raise HTTPException(status_code=500, detail="Failed to sync configs") from e


class TestLocalModelRequest(BaseModel):
    model: str
    base_url: str | None = None
    api_key: str | None = None


class TestLocalModelResponse(BaseModel):
    success: bool
    message: str
    latency_ms: int


@router.post("/test-local-model", response_model=TestLocalModelResponse)
async def test_local_model(request: TestLocalModelRequest) -> TestLocalModelResponse:
    """Test connectivity to a local LLM (e.g. Ollama).

    Sends a minimal request to verify the model is reachable and responsive.
    """
    from langchain_core.messages import HumanMessage
    from myrm_agent_harness.toolkits.llms import create_litellm_model

    start = time.monotonic()
    try:
        llm = create_litellm_model(
            model=request.model,
            base_url=request.base_url,
            api_key=request.api_key or "",
            temperature=0.0,
            streaming=False,
        )
        await llm.ainvoke(
            [HumanMessage(content="hi")],
            config={"max_tokens": 1, "timeout": 5},
        )
        elapsed = int((time.monotonic() - start) * 1000)
        return TestLocalModelResponse(success=True, message="OK", latency_ms=elapsed)
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return TestLocalModelResponse(
            success=False,
            message=f"{type(exc).__name__}: {exc}",
            latency_ms=elapsed,
        )


_CREDENTIAL_KEY_TO_CHANNEL: dict[str, str] = {
    "telegramCredentials": "telegram",
    "feishuCredentials": "feishu",
    "dingtalkCredentials": "dingtalk",
    "slackCredentials": "slack",
    "qqCredentials": "qq",
    "discordCredentials": "discord",
    "wecomCredentials": "wecom",
    "wecomAibotCredentials": "wecom_aibot",
    "teamsCredentials": "teams",
    "matrixCredentials": "matrix",
    "googlechatCredentials": "googlechat",
    "voiceCredentials": "voice",
    "signalCredentials": "signal",
    "lineCredentials": "line",
    "imessageCredentials": "imessage",
    "ircCredentials": "irc",
    "zaloCredentials": "zalo",
    "emailCredentials": "email",
    "mattermostCredentials": "mattermost",
    "wechatCredentials": "wechat",
    "whatsappCredentials": "whatsapp",
    "smsCredentials": "sms",
}


async def _try_hot_register_channel(config_key: str) -> None:
    """Hot-register a channel after its credentials are saved.

    If the channel is already registered in the gateway, it will be removed and re-added
    to apply the new credentials (hot-reload).
    If the channel has valid credentials, creates and adds it via hot-add.
    Failures are logged but never propagate to the caller.
    """
    channel_name = _CREDENTIAL_KEY_TO_CHANNEL.get(config_key)
    if not channel_name:
        return

    try:
        from app.core.channel_bridge import channel_gateway

        if channel_gateway.bus.get_channel(channel_name):
            # Remove the existing channel first to allow hot-reload
            await channel_gateway.remove_channel(channel_name)

        from app.channels.core.credentials import resolve_credentials
        from app.channels.providers.registry import get_channel_class_safe
        from app.core.channel_bridge.credential_spec import is_channel_enabled, load_from_db

        cls = get_channel_class_safe(channel_name)
        if cls is None or cls.credential_spec is None:
            return

        creds = await resolve_credentials(cls.credential_spec, load_from_db)
        if not any(creds.values()):
            return

        instance = cls.from_credentials(creds)

        enabled = await is_channel_enabled(cls.credential_spec.config_key)
        if not enabled:
            from app.channels.types import ChannelStatus

            instance._status = ChannelStatus.DISABLED

        await channel_gateway.add_channel(instance)
        logger.info("Channel '%s' hot-registered after credential save", channel_name)
    except Exception:
        logger.debug("Hot-register channel '%s' failed (non-critical)", channel_name, exc_info=True)
