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

import asyncio
import logging
import time
from pathlib import Path
from typing import get_args

from fastapi import APIRouter, HTTPException, Query, Request
from filelock import FileLock, Timeout
from pydantic import BaseModel, Field, ValidationError

from app.api.config.pricing import pricing_router
from app.api.config.privacy_preview import privacy_preview_router
from app.api.config.telegram_onboarding import telegram_onboarding_router
from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
from app.core.infra.ingress_requirement import invalidate_ingress_requirement_cache
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
from app.services.channels import credential_reload
from app.services.config.service import VersionConflictError, config_service
from app.services.integrations.search_verify import invalidate_search_verify_cache

logger = logging.getLogger(__name__)

_READINESS_DB_TIMEOUT_DEFAULT_SEC = 2.5
_READINESS_DB_TIMEOUT_DEV_SEC = 15.0


def _readiness_db_timeout_sec() -> float:
    """Parallel E2E sqlite contention — 2.5s causes perpetual config_load_timeout."""
    import os

    override = os.environ.get("MYRM_READINESS_DB_TIMEOUT_SEC", "").strip()
    if override:
        try:
            return max(_READINESS_DB_TIMEOUT_DEFAULT_SEC, float(override))
        except ValueError:
            pass
    from app.server.runtime_dev_info import get_runtime_dev_info

    if get_runtime_dev_info()["dev_mode"] == "split_dev":
        return _READINESS_DB_TIMEOUT_DEV_SEC
    return _READINESS_DB_TIMEOUT_DEFAULT_SEC


router = APIRouter()

_VALID_CONFIG_KEYS: frozenset[str] = frozenset(get_args(ConfigKey))


_SECOND_BRAIN_APPLY_LOCK = asyncio.Lock()
_SECOND_BRAIN_CROSS_PROCESS_LOCK_TIMEOUT_SEC = 0.0
_SECOND_BRAIN_ONBOARDING_IN_PROGRESS_CODE = "SECOND_BRAIN_ONBOARDING_IN_PROGRESS"
_SECOND_BRAIN_ONBOARDING_IN_PROGRESS_MESSAGE = "Second Brain preset apply is already in progress. Please retry shortly."


def _second_brain_apply_lock_path() -> Path:
    from app.config.settings import settings

    lock_dir = Path(settings.database.state_dir) / "locks" / "onboarding"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / "second-brain-preset.lock"


def _acquire_second_brain_cross_process_lock(lock: FileLock) -> None:
    try:
        lock.acquire(timeout=_SECOND_BRAIN_CROSS_PROCESS_LOCK_TIMEOUT_SEC)
    except Timeout as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": _SECOND_BRAIN_ONBOARDING_IN_PROGRESS_CODE,
                "message": _SECOND_BRAIN_ONBOARDING_IN_PROGRESS_MESSAGE,
            },
        ) from exc


def _release_second_brain_cross_process_lock(lock: FileLock) -> None:
    if lock.is_locked:
        lock.release()


def _validate_config_value(config_key: str, value: dict[str, object], *, operation: str) -> dict[str, object]:
    model_class = OMNI_CONFIG_MODELS.get(config_key)
    if not model_class:
        return value

    if config_key == "searchServices" and isinstance(value, dict):
        raw_configs = value.get("searchServiceConfigs")
        if isinstance(raw_configs, list):
            from app.core.integrations.search_catalog.migration import (
                migrate_search_service_configs,
            )

            dict_rows = [row for row in raw_configs if isinstance(row, dict)]
            value = {
                **value,
                "searchServiceConfigs": migrate_search_service_configs(dict_rows),
            }

    try:
        validated_data = model_class.model_validate(value)
    except ValidationError as exc:
        logger.warning("Omni-Config %s validation failed for %s: %s", operation, config_key, exc)
        field_errors = [{"field": ".".join(str(s) for s in err["loc"]), "message": err["msg"]} for err in exc.errors()]
        raise HTTPException(
            status_code=422,
            detail={"message": "Configuration validation failed", "errors": field_errors},
        ) from exc
    except Exception as exc:
        logger.warning("Omni-Config %s validation failed for %s: %s", operation, config_key, exc)
        raise HTTPException(
            status_code=422,
            detail="Configuration validation failed",
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
    keys: str | None = Query(None, description="按需加载，逗号分隔的配置键，如 providers,chatSettings"),
) -> AllConfigsResponse:
    """获取配置

    Args:
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
    from app.core.channel_bridge.config_readiness import (
        ProviderConfigChecker,
        SearchConfigChecker,
        load_readiness_inputs,
    )
    from app.database.connection import get_session
    from app.services.config.onboarding import check_onboarding_status

    try:
        providers_dict, search_configured = await asyncio.wait_for(
            load_readiness_inputs(),
            timeout=_readiness_db_timeout_sec(),
        )
    except TimeoutError:
        logger.warning(
            "Readiness config load timed out after %.1fs; returning degraded snapshot",
            _readiness_db_timeout_sec(),
        )
        return {
            "provider": {
                "is_ready": False,
                "missing_items": ["config_load_timeout"],
                "suggestions": ["Backend is busy; retry shortly"],
            },
            "search": {
                "is_ready": False,
                "missing_items": ["config_load_timeout"],
                "suggestions": ["Backend is busy; retry shortly"],
            },
            "onboarding_completed": True,
            "degraded": True,
        }
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
            "onboarding_completed": True,
            "degraded": True,
        }

    provider_checker = ProviderConfigChecker()
    provider_result = provider_checker.check(providers_dict)

    search_checker = SearchConfigChecker()
    if search_configured:
        search_result = search_checker.check({"searchServiceConfigs": [{"enabled": True}]})
    else:
        search_result = search_checker.check(None)

    onboarding_completed = True
    degraded = False
    try:

        async def _load_onboarding_completed() -> bool:
            async with get_session() as db:
                return await check_onboarding_status(db, "sandbox")

        onboarding_completed = await asyncio.wait_for(
            _load_onboarding_completed(),
            timeout=_readiness_db_timeout_sec(),
        )
    except TimeoutError:
        logger.warning(
            "Readiness onboarding check timed out after %.1fs; assuming completed to avoid shell stall",
            _readiness_db_timeout_sec(),
        )
        onboarding_completed = True
        degraded = True
    except Exception as exc:
        logger.warning("Readiness onboarding check failed: %s", exc)
        degraded = True

    return {
        "provider": provider_result.to_dict(),
        "search": search_result.to_dict(),
        "onboarding_completed": onboarding_completed,
        "degraded": degraded,
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


@router.get("/onboarding/second-brain/status")
async def get_second_brain_onboarding_status(request: Request) -> dict[str, object]:
    """Return Second Brain preset checklist (agent, cron, vault, provider)."""
    from app.services.onboarding.second_brain_preset import (
        get_second_brain_preset_status,
    )

    accept_lang = request.headers.get("Accept-Language", "en")
    status = await get_second_brain_preset_status(accept_language=accept_lang)
    return status.model_dump()


@router.post("/onboarding/second-brain/apply")
async def apply_second_brain_onboarding(request: Request) -> dict[str, object]:
    """Apply Second Brain preset: user agent + read-it-later cron + checklist state."""
    from app.services.onboarding.second_brain_preset import (
        SecondBrainPresetError,
        apply_second_brain_preset,
    )

    accept_lang = request.headers.get("Accept-Language", "en")
    async with _SECOND_BRAIN_APPLY_LOCK:
        cross_process_lock = FileLock(str(_second_brain_apply_lock_path()))
        _acquire_second_brain_cross_process_lock(cross_process_lock)
        try:
            result = await apply_second_brain_preset(accept_language=accept_lang)
        except FileNotFoundError as exc:
            logger.warning("Second Brain preset file not found: %s", exc)
            raise HTTPException(status_code=500, detail="Preset file not found") from exc
        except SecondBrainPresetError as exc:
            raise HTTPException(status_code=500, detail=exc.message) from exc
        except Exception as exc:
            logger.exception("Failed to apply Second Brain preset")
            raise HTTPException(status_code=500, detail="Failed to apply Second Brain preset") from exc
        finally:
            _release_second_brain_cross_process_lock(cross_process_lock)
    return result.model_dump()


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


_TINY_VISION_HEALTH_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


class VisionHealthResult(BaseModel):
    """Result of a vision fallback chain health probe."""

    configured: bool = Field(..., description="Whether visionFallbackModel is configured")
    healthy: bool = Field(..., description="Whether the vision model successfully analyzed a test image")
    latency_ms: int | None = Field(default=None, description="Vision probe latency in milliseconds")
    error: str | None = Field(default=None, description="Error message when unhealthy")
    model: str | None = Field(default=None, description="Configured primary LiteLLM model id")
    resolved_model: str | None = Field(
        default=None,
        description="LiteLLM model id that actually succeeded during the probe",
    )
    base_url: str | None = Field(default=None, description="Resolved API base URL when unhealthy")


@router.post("/vision-health", response_model=VisionHealthResult)
async def vision_health_check() -> VisionHealthResult:
    """Probe the configured vision fallback chain with a tiny test image."""
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.channel_bridge.config_parsers import (
        build_vision_fallback_engine_from_providers,
        extract_vision_fallback_model_config,
    )

    user_cfgs = await load_user_configs()
    model_cfg = extract_vision_fallback_model_config(user_cfgs.providers_dict)
    if model_cfg is None:
        return VisionHealthResult(
            configured=False,
            healthy=False,
            error="Vision fallback model is not configured",
        )

    try:
        engine = build_vision_fallback_engine_from_providers(user_cfgs.providers_dict)
        if engine is None:
            return VisionHealthResult(
                configured=False,
                healthy=False,
                error="Vision fallback model is not configured",
            )
        from myrm_agent_harness.toolkits.llms.vision.fallback_engine import (
            VisionDescriptionError,
        )

        start = time.monotonic()
        try:
            await engine.describe_image_b64(
                _TINY_VISION_HEALTH_PNG_B64,
                "image/png",
                prompt="Health check",
            )
        except VisionDescriptionError as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            resolved_model = engine.last_success_model or model_cfg.model
            return VisionHealthResult(
                configured=True,
                healthy=False,
                latency_ms=latency_ms,
                error=str(exc),
                model=model_cfg.model,
                resolved_model=(resolved_model if resolved_model != model_cfg.model else None),
                base_url=model_cfg.base_url,
            )
        latency_ms = int((time.monotonic() - start) * 1000)
        resolved_model = engine.last_success_model or model_cfg.model
        return VisionHealthResult(
            configured=True,
            healthy=True,
            latency_ms=latency_ms,
            model=model_cfg.model,
            resolved_model=(resolved_model if resolved_model != model_cfg.model else None),
        )
    except Exception as exc:
        logger.warning("Vision fallback health check failed: %s", exc)
        return VisionHealthResult(
            configured=True,
            healthy=False,
            error=str(exc),
            model=model_cfg.model,
            base_url=model_cfg.base_url,
        )


VideoHealthResult = VisionHealthResult


@router.post("/video-health", response_model=VideoHealthResult)
async def video_health_check() -> VideoHealthResult:
    """Probe the configured video fallback chain with a tiny test image."""
    from myrm_agent_harness.toolkits.llms.vision.fallback_engine import (
        VisionDescriptionError,
    )

    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.channel_bridge.config_parsers import (
        build_video_fallback_probe_engine_from_providers,
        extract_video_fallback_model_config,
    )

    user_cfgs = await load_user_configs()
    model_cfg = extract_video_fallback_model_config(user_cfgs.providers_dict)
    if model_cfg is None:
        return VideoHealthResult(
            configured=False,
            healthy=False,
            error="Video fallback model is not configured",
        )

    try:
        engine = build_video_fallback_probe_engine_from_providers(user_cfgs.providers_dict)
        if engine is None:
            return VideoHealthResult(
                configured=False,
                healthy=False,
                error="Video fallback model is not configured",
            )

        start = time.monotonic()
        try:
            await engine.describe_image_b64(
                _TINY_VISION_HEALTH_PNG_B64,
                "image/png",
                prompt="Health check",
            )
        except VisionDescriptionError as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            resolved_model = engine.last_success_model or model_cfg.model
            return VideoHealthResult(
                configured=True,
                healthy=False,
                latency_ms=latency_ms,
                error=str(exc),
                model=model_cfg.model,
                resolved_model=(resolved_model if resolved_model != model_cfg.model else None),
                base_url=model_cfg.base_url,
            )
        latency_ms = int((time.monotonic() - start) * 1000)
        resolved_model = engine.last_success_model or model_cfg.model
        return VideoHealthResult(
            configured=True,
            healthy=True,
            latency_ms=latency_ms,
            model=model_cfg.model,
            resolved_model=(resolved_model if resolved_model != model_cfg.model else None),
        )
    except Exception as exc:
        logger.warning("Video fallback health check failed: %s", exc)
        return VideoHealthResult(
            configured=True,
            healthy=False,
            error=str(exc),
            model=model_cfg.model,
            base_url=model_cfg.base_url,
        )


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

    searxng_hit = next(
        (s for s in search_results if s.get("provider") == "searxng" and s.get("available")),
        None,
    )

    return {
        "results": [r.model_dump() for r in results],
        "has_available": len(available_results) > 0,
        "recommended_model": recommended_model,
        "search": search_results,
        "search_has_available": searxng_hit is not None,
        "recommended_searxng_url": (str(searxng_hit.get("base_url")) if searxng_hit else get_default_searxng_api_base()),
    }


router.include_router(pricing_router)
router.include_router(privacy_preview_router)
router.include_router(telegram_onboarding_router)


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
        if config_key == "retrieval":
            from app.services.faq.factory import reset_faq_interceptor

            reset_faq_interceptor()
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


class TestLocalModelRequest(BaseModel):
    model: str
    base_url: str | None = None
    api_key: str | None = None


class TestLocalModelResponse(BaseModel):
    success: bool
    message: str
    latency_ms: int


# Stays below the 15 s request abort of the settings UI so a slow model is reported with a
# classified message instead of the page giving up first.
_LOCAL_MODEL_TEST_TIMEOUT_S = 12.0


def _classify_local_model_error(exc: Exception) -> str:
    """Map internal exceptions to user-friendly connection test messages."""
    if isinstance(exc, TimeoutError):
        # The request deadline expired without an answer: a model that is still loading is
        # indistinguishable from a wrong address, so the message names both.
        return (
            f"No response within {_LOCAL_MODEL_TEST_TIMEOUT_S:g} seconds"
            " — the model may still be loading, or check the server address"
        )
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    if "refused" in msg or "connectionrefused" in name:
        return "Connection refused — is the model server running?"
    if "timeout" in msg or "timed out" in msg or "timeout" in name:
        return "Connection timed out — check the server address"
    if "401" in msg or "unauthorized" in msg or "auth" in name:
        return "Authentication failed — check your API key"
    if "404" in msg or "not found" in msg:
        return "Model not found — check the model name"
    if "dns" in msg or "name resolution" in msg or "getaddrinfo" in msg:
        return "DNS resolution failed — check the base URL"
    if "ssl" in msg or "certificate" in msg:
        return "SSL/TLS error — check your server's certificate"
    return "Connection test failed"


@router.post("/test-local-model", response_model=TestLocalModelResponse)
async def test_local_model(request: TestLocalModelRequest) -> TestLocalModelResponse:
    """Test connectivity to a local LLM (e.g. Ollama).

    Sends a minimal request to verify the model is reachable and responsive; the request is
    abandoned after ``_LOCAL_MODEL_TEST_TIMEOUT_S`` seconds.
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
        await asyncio.wait_for(
            llm.ainvoke([HumanMessage(content="hi")]),
            timeout=_LOCAL_MODEL_TEST_TIMEOUT_S,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        return TestLocalModelResponse(success=True, message="OK", latency_ms=elapsed)
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        logger.warning("Local model test failed: %s: %s", type(exc).__name__, exc)
        user_msg = _classify_local_model_error(exc)
        return TestLocalModelResponse(
            success=False,
            message=user_msg,
            latency_ms=elapsed,
        )


class TestProxyRequest(BaseModel):
    proxy_url: str = Field(..., description="Proxy URL to test (http, https, socks5, socks5h)")
    target_url: str | None = Field(default=None, description="Optional target URL to probe through proxy")


class TestProxyResponse(BaseModel):
    success: bool
    latency_ms: int | None = None
    error: str | None = None


@router.post("/test-proxy", response_model=TestProxyResponse)
async def test_proxy(request: TestProxyRequest) -> TestProxyResponse:
    """Test outbound connectivity of an egress proxy.

    Validates URL schema, credentials, and probes connectivity to target URL.
    """
    from myrm_agent_harness.toolkits.llms.utils.proxy import (
        probe_proxy_health,
        validate_proxy_url,
    )

    is_valid, err_msg = validate_proxy_url(request.proxy_url)
    if not is_valid:
        return TestProxyResponse(
            success=False,
            error=err_msg or "Invalid proxy URL",
        )

    target = (request.target_url or "").strip() or "https://1.1.1.1"
    start = time.monotonic()
    success, err_msg = await probe_proxy_health(
        proxy_url=request.proxy_url,
        target_url=target,
        timeout_s=5.0,
        cache_ttl_s=0.0,
    )
    elapsed = int((time.monotonic() - start) * 1000)

    return TestProxyResponse(
        success=success,
        latency_ms=elapsed if success else None,
        error=err_msg if not success else None,
    )


async def _hot_reload_cloud_browser(value: dict[str, object]) -> None:
    """Hot-reload the browser pool's remote endpoint after cloud browser config changes."""
    try:
        from app.config.browser import get_configured_browser_pool
        from app.schemas.config import BrowserCloudProviderConfigValue

        config = BrowserCloudProviderConfigValue.model_validate(value)
        endpoint = config.resolve_ws_endpoint()
        pool = get_configured_browser_pool()
        await pool.update_remote_endpoint(endpoint)
    except Exception:
        logger.debug("Hot-reload cloud browser endpoint failed (non-critical)", exc_info=True)


async def _hot_reload_browser_proxy(value: dict[str, object]) -> None:
    """Hot-reload the browser pool's proxy pool after browser proxy config changes."""
    try:
        from myrm_agent_harness.toolkits.browser.pool.proxy import RoundRobinProxyPool

        from app.config.browser import get_configured_browser_pool
        from app.schemas.config import BrowserProxyConfigValue

        config = BrowserProxyConfigValue.model_validate(value)
        proxy_pool = None
        if config.enabled and config.proxies:
            proxy_pool = RoundRobinProxyPool.from_urls(config.proxies)
        pool = get_configured_browser_pool()
        await pool.update_proxy_pool(proxy_pool)
    except Exception:
        logger.debug("Hot-reload browser proxy failed (non-critical)", exc_info=True)
