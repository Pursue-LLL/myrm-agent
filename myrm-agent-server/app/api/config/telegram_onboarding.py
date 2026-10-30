"""Telegram assistant onboarding endpoint.

[INPUT]
- app.services.config.service::config_service (POS: 配置核心业务逻辑服务)
- app.services.channels.credential_reload::reload_channel_credentials (POS: Business-layer step that makes a credentials save take effect without a restart)
- app.channels.providers.telegram.api::TelegramClient (POS: Telegram Bot API async HTTP client)
- app.services.agent.agent_service::AgentService (POS: 业务层Agent服务)

[OUTPUT]
- telegram_onboarding_router: ``POST /onboarding/telegram-assistant/apply`` mounted under the config router
- TelegramAssistantOnboardingRequest, TelegramAssistantOnboardingResponse: Wizard request and response payloads

[POS]
One-call Telegram setup for the onboarding wizard: verify the bot token (through the proxy typed or already saved),
resolve or create the bound agent, persist credentials, DM policy and topic binding, and restore every touched
setting if a later step fails. A token Telegram refused and a Bot API that could not be reached come back as
distinct ``400`` codes; a concurrent run returns ``409``.
"""

import asyncio
import hashlib
import logging
import time
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from filelock import FileLock, Timeout
from pydantic import BaseModel, Field

from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
from app.core.infra.ingress_requirement import invalidate_ingress_requirement_cache
from app.services.channels import credential_reload
from app.services.config.service import config_service

if TYPE_CHECKING:
    from myrm_agent_harness.backends.profiles.types import AgentProfile

logger = logging.getLogger(__name__)

telegram_onboarding_router = APIRouter()


class TelegramAssistantOnboardingRequest(BaseModel):
    """Zero-code Telegram assistant onboarding request payload."""

    bot_token: str = Field(..., alias="botToken", min_length=10, max_length=256)
    webhook_url: str | None = Field(default=None, alias="webhookUrl", max_length=2048)
    proxy: str | None = Field(
        default=None,
        max_length=2048,
        description="Forward proxy for Telegram traffic; blank keeps the proxy already saved",
    )
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
_TELEGRAM_ONBOARDING_IN_PROGRESS_MESSAGE = "Telegram onboarding is already in progress. Please retry shortly."


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
    proxy: str | None,
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

    if proxy:
        merged["proxy"] = proxy
    else:
        merged.pop("proxy", None)

    auto_topic = merged.get("autoTopic")
    merged["autoTopic"] = bool(auto_topic) if isinstance(auto_topic, bool) else True

    notifications_mode = merged.get("notificationsMode")
    if isinstance(notifications_mode, str) and notifications_mode in {
        "important",
        "all",
    }:
        merged["notificationsMode"] = notifications_mode
    else:
        merged["notificationsMode"] = "important"

    return merged


def _build_channels_config_with_open_telegram_dm(
    previous: dict[str, object] | None,
) -> dict[str, object]:
    cfg = deepcopy(previous) if previous is not None else {}
    channels_raw = cfg.get("channels")
    channels_map: dict[str, object] = {str(k): v for k, v in channels_raw.items()} if isinstance(channels_raw, dict) else {}

    telegram_raw = channels_map.get("telegram")
    telegram_cfg: dict[str, object] = {str(k): v for k, v in telegram_raw.items()} if isinstance(telegram_raw, dict) else {}
    telegram_cfg["dmPolicy"] = "open"
    channels_map["telegram"] = telegram_cfg
    cfg["channels"] = channels_map
    return cfg


def _stored_telegram_proxy(credentials: dict[str, object] | None) -> str | None:
    """The forward proxy saved with the Telegram credentials, if any."""
    proxy = credentials.get("proxy") if credentials else None
    return (proxy.strip() or None) if isinstance(proxy, str) else None


def _resolve_telegram_proxy(requested: str | None, credentials: dict[str, object] | None) -> str | None:
    """The proxy for this onboarding run: a typed one (validated, canonical scheme) wins; a blank one keeps the saved one."""
    from myrm_agent_harness.toolkits.llms.utils.proxy import normalize_proxy_url, validate_proxy_url

    typed = normalize_proxy_url(requested)
    if typed is None:
        return _stored_telegram_proxy(credentials)
    is_valid, reason = validate_proxy_url(typed)
    if not is_valid:
        raise HTTPException(status_code=422, detail={"code": "TELEGRAM_PROXY_REJECTED", "message": reason or "Invalid proxy URL"})
    return typed


async def _verify_telegram_token(bot_token: str, proxy: str | None) -> str:
    from app.channels.providers.telegram.api import TelegramClient

    client = TelegramClient(bot_token, proxy=proxy)
    try:
        me = await client.get_me()
    finally:
        await client.close()

    username = str(me.get("username", "")).strip()
    return username or "unknown"


def _telegram_verification_error(exc: Exception, proxy: str | None) -> HTTPException:
    """Tell a token Telegram refused from a Bot API this machine could not reach: the next step differs.

    An unreachable Bot API also says whether the check went through a proxy. The wizard never shows a saved proxy
    and a blank field keeps it, so only ``proxy`` (typed or saved) knows whether asking for one still makes sense.
    """
    from myrm_agent_harness.api import redact_sensitive_text

    from app.channels.providers.telegram.api_core import TelegramFailureReason, getme_failure_reason

    reason = getme_failure_reason(exc)
    logger.warning("Telegram onboarding token check failed (%s): %s", reason.value, redact_sensitive_text(str(exc)))
    if reason is TelegramFailureReason.TOKEN_REJECTED:
        return HTTPException(status_code=400, detail={"code": reason.value, "message": "Telegram rejected the bot token"})
    return HTTPException(
        status_code=400,
        detail={"code": reason.value, "message": "Telegram Bot API could not be reached", "viaProxy": proxy is not None},
    )


def _is_channel_bindable_agent(agent_profile: object) -> bool:
    metadata = getattr(agent_profile, "metadata", None)
    if not isinstance(metadata, dict):
        return True
    prompt_mode = metadata.get("prompt_mode")
    return not (isinstance(prompt_mode, str) and prompt_mode.lower() == "search")


def _pick_first_channel_bindable_agent(candidates: list["AgentProfile"]) -> "AgentProfile | None":
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
        cross_process_lock = FileLock(str(_telegram_agent_cross_process_lock_path(normalized_name)))
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
                "You are a practical personal assistant running on Telegram. Keep replies concise, actionable, and privacy-aware."
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
        await credential_reload.reload_channel_credentials("telegramCredentials")
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


@telegram_onboarding_router.post(
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

    previous_telegram, previous_channels, previous_topics = await asyncio.gather(
        config_service.get("telegramCredentials"),
        config_service.get("channels"),
        config_service.get("telegramTopics"),
    )
    snapshot = _TelegramOnboardingSnapshot(
        telegram_credentials=(deepcopy(previous_telegram.value) if previous_telegram else None),
        channels_config=(deepcopy(previous_channels.value) if previous_channels else None),
        telegram_topics=deepcopy(previous_topics.value) if previous_topics else None,
    )

    proxy = _resolve_telegram_proxy(body.proxy, snapshot.telegram_credentials)
    try:
        bot_username = await _verify_telegram_token(bot_token, proxy)
    except Exception as exc:
        raise _telegram_verification_error(exc, proxy) from exc

    created_agent_id: str | None = None
    try:
        agent_id, agent_name, created_agent_id = await _resolve_or_create_telegram_agent(body)

        telegram_credentials = _build_telegram_credentials(snapshot.telegram_credentials, body, proxy)
        await config_service.set(
            config_key="telegramCredentials",
            value=telegram_credentials,
            device_id=_ONBOARDING_DEVICE_ID,
        )
        invalidate_user_configs_cache()
        invalidate_ingress_requirement_cache()
        await credential_reload.reload_channel_credentials("telegramCredentials")

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
        botUsername=bot_username,
        agentId=agent_id,
        agentName=agent_name,
        channelEnabled=True,
        connected=connected,
        status=status,
    )
