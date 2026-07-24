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
import hashlib
import logging
import time
from copy import deepcopy
from pathlib import Path
from typing import get_args

from fastapi import APIRouter, HTTPException, Query
from filelock import FileLock, Timeout
from pydantic import BaseModel, Field

from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
from app.core.channel_bridge.config_parsers import invalidate_search_health_cache
from app.core.infra.ingress_requirement import invalidate_ingress_requirement_cache
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

_READINESS_DB_TIMEOUT_SEC = 2.5

router = APIRouter()

_VALID_CONFIG_KEYS: frozenset[str] = frozenset(get_args(ConfigKey))


class TelegramAssistantOnboardingRequest(BaseModel):
    """Zero-code Telegram assistant onboarding request payload."""

    bot_token: str = Field(..., alias="botToken", min_length=10, max_length=256)
    webhook_url: str | None = Field(None, alias="webhookUrl", max_length=2048)
    assistant_name: str = Field(
        default="Personal Telegram Assistant",
        alias="assistantName",
        min_length=1,
        max_length=255,
    )
    assistant_description: str | None = Field(
        default=None,
        alias="assistantDescription",
        max_length=1024,
    )
    assistant_system_prompt: str | None = Field(
        default=None,
        alias="assistantSystemPrompt",
        max_length=8000,
    )

    class Config:
        populate_by_name = True


class TelegramAssistantOnboardingResponse(BaseModel):
    """Zero-code Telegram assistant onboarding response payload."""

    success: bool
    message: str
    bot_username: str = Field(..., alias="botUsername")
    agent_id: str = Field(..., alias="agentId")
    agent_name: str = Field(..., alias="agentName")
    channel_enabled: bool = Field(..., alias="channelEnabled")
    connected: bool
    status: str

    class Config:
        populate_by_name = True


class _TelegramOnboardingSnapshot(BaseModel):
    """Best-effort rollback snapshot for onboarding mutations."""

    telegram_credentials: dict[str, object] | None
    channels_config: dict[str, object] | None
    telegram_topics: dict[str, object] | None


_ONBOARDING_DEVICE_ID = "onboarding-wizard"
_TELEGRAM_AGENT_RESOLUTION_LOCK = asyncio.Lock()
_TELEGRAM_AGENT_CROSS_PROCESS_LOCK_TIMEOUT_SEC = 0.0
_TELEGRAM_ONBOARDING_IN_PROGRESS_CODE = "TELEGRAM_ONBOARDING_IN_PROGRESS"
_TELEGRAM_ONBOARDING_IN_PROGRESS_MESSAGE = (
    "Telegram onboarding is already in progress. Please retry shortly."
)


def _normalize_telegram_agent_name(raw: str) -> str:
    return raw.strip().casefold()


def _telegram_agent_cross_process_lock_path(assistant_name: str) -> Path:
    from app.config.settings import settings

    normalized_name = _normalize_telegram_agent_name(assistant_name)
    lock_hash = hashlib.sha256(normalized_name.encode("utf-8")).hexdigest()
    lock_dir = Path(settings.database.state_dir) / "locks" / "onboarding"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / f"telegram-agent-{lock_hash}.lock"


def _acquire_telegram_agent_cross_process_lock(lock: FileLock) -> None:
    try:
        lock.acquire(timeout=_TELEGRAM_AGENT_CROSS_PROCESS_LOCK_TIMEOUT_SEC)
    except Timeout as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": _TELEGRAM_ONBOARDING_IN_PROGRESS_CODE,
                "message": _TELEGRAM_ONBOARDING_IN_PROGRESS_MESSAGE,
            },
        ) from exc


def _release_telegram_agent_cross_process_lock(lock: FileLock) -> None:
    if lock.is_locked:
        lock.release()


def _normalize_webhook_url(raw: str | None) -> str:
    if raw is None:
        return ""
    return raw.strip()


def _assert_webhook_url_valid(raw: str) -> None:
    if raw and not raw.startswith("https://"):
        raise HTTPException(status_code=422, detail="Telegram webhook URL must start with https://")


def _build_telegram_credentials(
    previous: dict[str, object] | None,
    request: TelegramAssistantOnboardingRequest,
) -> dict[str, object]:
    merged = deepcopy(previous) if previous is not None else {}
    merged["botToken"] = request.bot_token.strip()
    merged["enabled"] = True
    merged["botPolicy"] = "mention_only"

    webhook_url = _normalize_webhook_url(request.webhook_url)
    if webhook_url:
        merged["webhookUrl"] = webhook_url
    else:
        merged["webhookUrl"] = ""

    auto_topic = merged.get("autoTopic")
    merged["autoTopic"] = bool(auto_topic) if isinstance(auto_topic, bool) else True

    notifications_mode = merged.get("notificationsMode")
    if isinstance(notifications_mode, str) and notifications_mode in {"important", "all"}:
        merged["notificationsMode"] = notifications_mode
    else:
        merged["notificationsMode"] = "important"

    return merged


def _build_channels_config_with_open_telegram_dm(previous: dict[str, object] | None) -> dict[str, object]:
    cfg = deepcopy(previous) if previous is not None else {}
    channels_raw = cfg.get("channels")
    channels_map: dict[str, object] = {str(k): v for k, v in channels_raw.items()} if isinstance(channels_raw, dict) else {}

    telegram_raw = channels_map.get("telegram")
    telegram_cfg: dict[str, object] = (
        {str(k): v for k, v in telegram_raw.items()} if isinstance(telegram_raw, dict) else {}
    )
    telegram_cfg["dmPolicy"] = "open"
    channels_map["telegram"] = telegram_cfg
    cfg["channels"] = channels_map
    return cfg


async def _verify_telegram_token(bot_token: str) -> str:
    from app.channels.providers.telegram.api import TelegramClient

    client = TelegramClient(bot_token)
    try:
        me = await client.get_me()
    finally:
        await client.close()

    username = str(me.get("username", "")).strip()
    return username or "unknown"


def _is_channel_bindable_agent(agent_profile: object) -> bool:
    metadata = getattr(agent_profile, "metadata", None)
    if not isinstance(metadata, dict):
        return True
    prompt_mode = metadata.get("prompt_mode")
    return not (isinstance(prompt_mode, str) and prompt_mode.lower() == "search")


def _pick_first_channel_bindable_agent(candidates: list[object]) -> object | None:
    for candidate in candidates:
        if _is_channel_bindable_agent(candidate):
            return candidate
    return None


async def _resolve_or_create_telegram_agent(
    request: TelegramAssistantOnboardingRequest,
) -> tuple[str, str, str | None]:
    from app.database.dto import AgentCreate
    from app.services.agent.agent_service import AgentService

    normalized_name = request.assistant_name.strip()
    if not normalized_name:
        raise HTTPException(status_code=422, detail="Assistant name is required")
    normalized_description = (request.assistant_description or "").strip()
    normalized_system_prompt = (request.assistant_system_prompt or "").strip()

    async with _TELEGRAM_AGENT_RESOLUTION_LOCK:
        cross_process_lock = FileLock(
            str(_telegram_agent_cross_process_lock_path(normalized_name))
        )
        _acquire_telegram_agent_cross_process_lock(cross_process_lock)
        try:
            name_matches = await AgentService.get_agents_by_name(normalized_name)
            existing_bindable = _pick_first_channel_bindable_agent(name_matches)
            if existing_bindable is not None:
                existing_id = str(existing_bindable.id)
                existing_name = str(getattr(existing_bindable, "display_name", "") or normalized_name)
                return existing_id, existing_name, None

            create_name = normalized_name
            if name_matches:
                create_name = f"{normalized_name} (General)"
                general_name_matches = await AgentService.get_agents_by_name(create_name)
                existing_general = _pick_first_channel_bindable_agent(general_name_matches)
                if existing_general is not None:
                    existing_id = str(existing_general.id)
                    existing_name = str(getattr(existing_general, "display_name", "") or create_name)
                    return existing_id, existing_name, None

            default_description = "Personal Telegram assistant created by onboarding wizard."
            default_system_prompt = (
                "You are a practical personal assistant running on Telegram. "
                "Keep replies concise, actionable, and privacy-aware."
            )

            created = await AgentService.create_agent(
                AgentCreate(
                    name=create_name,
                    description=normalized_description or default_description,
                    system_prompt=normalized_system_prompt or default_system_prompt,
                    prompt_mode="full",
                    agent_type="individual",
                )
            )
            return created.id, created.display_name or create_name, created.id
        finally:
            _release_telegram_agent_cross_process_lock(cross_process_lock)


async def _wait_for_telegram_channel_state(
    timeout_seconds: float = 3.0,
    poll_interval_seconds: float = 0.2,
) -> tuple[bool, str]:
    from app.channels import ChannelStatus
    from app.core.channel_bridge import channel_gateway, check_channel_connected

    deadline = time.monotonic() + max(timeout_seconds, poll_interval_seconds)
    status = "unknown"
    connected = False

    while time.monotonic() <= deadline:
        channel = channel_gateway.bus.get_channel("telegram")
        if channel is not None:
            status = channel.status.value
            if channel.status in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
                connected = check_channel_connected(channel)
                return connected, status
        await asyncio.sleep(poll_interval_seconds)

    channel = channel_gateway.bus.get_channel("telegram")
    if channel is not None:
        status = channel.status.value
        connected = check_channel_connected(channel)
    return connected, status


async def _restore_config_snapshot(config_key: str, value: dict[str, object] | None) -> None:
    if value is None:
        await config_service.delete(config_key)
    else:
        await config_service.set(
            config_key=config_key,
            value=value,
            device_id=f"{_ONBOARDING_DEVICE_ID}-rollback",
        )


async def _rollback_telegram_onboarding(
    snapshot: _TelegramOnboardingSnapshot,
    created_agent_id: str | None,
) -> None:
    rollback_errors: list[str] = []

    try:
        await _restore_config_snapshot("telegramTopics", snapshot.telegram_topics)
    except Exception as exc:
        rollback_errors.append(f"topics restore failed: {exc}")

    try:
        await _restore_config_snapshot("channels", snapshot.channels_config)
        from app.core.channel_bridge.channel_policy import SqlChannelPolicyProvider
        from app.core.channel_bridge.setup import refresh_reaction_policy

        SqlChannelPolicyProvider._invalidate_cache()
        await refresh_reaction_policy()
    except Exception as exc:
        rollback_errors.append(f"channels restore failed: {exc}")

    try:
        await _restore_config_snapshot("telegramCredentials", snapshot.telegram_credentials)
        invalidate_user_configs_cache()
        invalidate_ingress_requirement_cache()
        await _try_hot_register_channel("telegramCredentials")
    except Exception as exc:
        rollback_errors.append(f"telegram credentials restore failed: {exc}")

    if created_agent_id:
        try:
            from app.services.agent.agent_service import AgentService

            await AgentService.delete_agent(created_agent_id)
        except Exception as exc:
            rollback_errors.append(f"agent cleanup failed: {exc}")

    if rollback_errors:
        logger.error(
            "Telegram onboarding rollback completed with issues: %s",
            "; ".join(rollback_errors),
        )


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
        user_configs = await asyncio.wait_for(
            load_user_configs(),
            timeout=_READINESS_DB_TIMEOUT_SEC,
        )
    except TimeoutError:
        logger.warning(
            "Readiness config load timed out after %.1fs; returning degraded snapshot",
            _READINESS_DB_TIMEOUT_SEC,
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
    provider_result = provider_checker.check(user_configs.providers_dict)

    search_checker = SearchConfigChecker()
    if user_configs.search_is_user_configured:
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
            timeout=_READINESS_DB_TIMEOUT_SEC,
        )
    except TimeoutError:
        logger.warning(
            "Readiness onboarding check timed out after %.1fs; assuming completed to avoid shell stall",
            _READINESS_DB_TIMEOUT_SEC,
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


@router.post(
    "/onboarding/telegram-assistant/apply",
    response_model=TelegramAssistantOnboardingResponse,
)
async def apply_telegram_assistant_onboarding(
    body: TelegramAssistantOnboardingRequest,
) -> TelegramAssistantOnboardingResponse:
    """Apply zero-code Telegram assistant onboarding in one atomic flow."""

    bot_token = body.bot_token.strip()
    if not bot_token:
        raise HTTPException(status_code=422, detail="Telegram bot token is required")

    webhook_url = _normalize_webhook_url(body.webhook_url)
    _assert_webhook_url_valid(webhook_url)

    try:
        bot_username = await _verify_telegram_token(bot_token)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Telegram token verification failed: {exc}") from exc

    previous_telegram, previous_channels, previous_topics = await asyncio.gather(
        config_service.get("telegramCredentials"),
        config_service.get("channels"),
        config_service.get("telegramTopics"),
    )
    snapshot = _TelegramOnboardingSnapshot(
        telegram_credentials=deepcopy(previous_telegram.value) if previous_telegram else None,
        channels_config=deepcopy(previous_channels.value) if previous_channels else None,
        telegram_topics=deepcopy(previous_topics.value) if previous_topics else None,
    )

    created_agent_id: str | None = None
    try:
        agent_id, agent_name, created_agent_id = await _resolve_or_create_telegram_agent(body)

        telegram_credentials = _build_telegram_credentials(snapshot.telegram_credentials, body)
        await config_service.set(
            config_key="telegramCredentials",
            value=telegram_credentials,
            device_id=_ONBOARDING_DEVICE_ID,
        )
        invalidate_user_configs_cache()
        invalidate_ingress_requirement_cache()
        await _try_hot_register_channel("telegramCredentials")

        channels_cfg = _build_channels_config_with_open_telegram_dm(snapshot.channels_config)
        await config_service.set(
            config_key="channels",
            value=channels_cfg,
            device_id=_ONBOARDING_DEVICE_ID,
        )
        invalidate_user_configs_cache()
        invalidate_ingress_requirement_cache()
        from app.core.channel_bridge.channel_policy import SqlChannelPolicyProvider
        from app.core.channel_bridge.setup import refresh_reaction_policy

        SqlChannelPolicyProvider._invalidate_cache()
        await refresh_reaction_policy()

        from app.channels.types.thread_sharing import ThreadSharingMode
        from app.core.channel_bridge.topic_config import SqlTopicManager

        topic_manager = SqlTopicManager()
        await topic_manager.bind_topic(
            channel="telegram",
            chat_id="__global__",
            thread_id=None,
            agent_id=agent_id,
            thread_sharing_mode=ThreadSharingMode.ISOLATED,
        )

        connected, status = await _wait_for_telegram_channel_state()
    except Exception as exc:
        logger.exception("Failed to apply Telegram onboarding package")
        await _rollback_telegram_onboarding(snapshot, created_agent_id)
        raise HTTPException(status_code=500, detail="Failed to apply Telegram onboarding package") from exc

    return TelegramAssistantOnboardingResponse(
        success=True,
        message="Telegram assistant onboarding applied successfully",
        bot_username=bot_username,
        agent_id=agent_id,
        agent_name=agent_name,
        channel_enabled=True,
        connected=connected,
        status=status,
    )


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
        invalidate_ingress_requirement_cache()
        if config_key == "providers":
            try:
                from app.core.skills.x_live_search_skill_enable import maybe_enable_x_live_search_skill

                providers_value = request.value if isinstance(request.value, dict) else None
                await maybe_enable_x_live_search_skill(providers_value)
            except Exception as exc:
                logger.warning("x-live-search skill auto-enable skipped: %s", exc)
        if config_key == "channels":
            from app.core.channel_bridge.channel_policy import SqlChannelPolicyProvider
            from app.core.channel_bridge.setup import refresh_reaction_policy

            SqlChannelPolicyProvider._invalidate_cache()
            await refresh_reaction_policy()
        if config_key.endswith("Credentials"):
            await _try_hot_register_channel(config_key)
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
        invalidate_ingress_requirement_cache()
        if config_key == "providers":
            try:
                from app.core.skills.x_live_search_skill_enable import maybe_enable_x_live_search_skill

                providers_value = new_value if isinstance(new_value, dict) else None
                await maybe_enable_x_live_search_skill(providers_value)
            except Exception as exc:
                logger.warning("x-live-search skill auto-enable skipped on rollback: %s", exc)
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
            invalidate_search_health_cache()
            invalidate_ingress_requirement_cache()
            if "channels" in result.new_versions:
                from app.core.channel_bridge.channel_policy import SqlChannelPolicyProvider
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
