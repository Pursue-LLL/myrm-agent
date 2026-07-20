"""Trigger unattended headless agent streams for goal continuation.

[INPUT]
- app.services.agent.streaming::ai_agent_service_stream (POS: General Agent SSE 流式桥接)
- app.core.channel_bridge.config_loader::load_user_configs (POS: WebUI 用户配置加载)
- myrm_agent_harness.agent.goals.protocols::GoalProvider (POS: Goal 生命周期协议)
- myrm_agent_harness.agent.goals.types::Goal (POS: Goal 数据类型)

[OUTPUT]
- trigger_goal_stream: fire-and-forget unattended stream task
- trigger_goal_stream_with_failure_policy: SSOT wrapper for setup + runtime failure handling
- handle_unattended_goal_stream_failure: NEEDS_HUMAN_REVIEW + SYSTEM_NOTIFICATION or keep ACTIVE

[POS]
Server-side headless goal continuation entry. Shared by dequeue, background WAIT resume, and loop restart.
Separated from streaming.py to keep the main streaming module under 500 lines.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from myrm_agent_harness.agent.goals.protocols import GoalProvider
    from myrm_agent_harness.agent.goals.types import Goal

logger = logging.getLogger(__name__)

_running_goal_tasks: set[asyncio.Task[None]] = set()

TriggerFailurePolicy = Literal["needs_human_review", "keep_active"]


async def _resolve_user_locale() -> str:
    """Load locale from personal settings (WebUI / Tauri / sandbox user config)."""
    from myrm_agent_harness.utils.locale import normalize_locale, resolve_locale

    from app.core.channel_bridge.config_loader import load_user_configs

    try:
        configs = await load_user_configs()
        ps = configs.personal_settings_dict if configs else None
        raw_locale = ps.get("locale") if ps else None
        if not raw_locale and ps:
            raw_locale = ps.get("language")
        locale_str = str(raw_locale) if raw_locale else None
        return resolve_locale(metadata_locale=locale_str, platform_locale=None, channel=None)
    except Exception:
        logger.debug("Failed to load user locale for goal stream failure", exc_info=True)
        return normalize_locale(None)


async def publish_goal_needs_review_notification(session_id: str, goal_id: str) -> None:
    """Publish goal_needs_review SSE after an unattended failure or orphan recovery."""
    from app.channels.i18n.engine import channel_t
    from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

    locale = await _resolve_user_locale()
    title = channel_t(locale, "goal_stream_failed_title")
    message = channel_t(locale, "goal_stream_failed_message")

    get_event_bus().publish(
        AppEvent(
            event_type=AppEventType.SYSTEM_NOTIFICATION,
            data={
                "title": title,
                "message": message,
                "meta_data": {
                    "kind": "goal_needs_review",
                    "chat_id": session_id,
                    "goal_id": goal_id,
                },
            },
        )
    )


async def _publish_goal_needs_review_notification(session_id: str, goal_id: str) -> None:
    await publish_goal_needs_review_notification(session_id, goal_id)


async def handle_unattended_goal_stream_failure(
    session_id: str,
    goal_id: str,
    provider: GoalProvider | None,
    *,
    on_failure: TriggerFailurePolicy,
    context: str,
) -> None:
    """Apply unattended stream failure policy — review state or Cron keep-active."""
    if on_failure == "keep_active":
        logger.error(
            "Goal %s remains ACTIVE for Cron fallback after %s failure",
            goal_id,
            context,
        )
        return

    if provider is None:
        logger.warning(
            "Cannot mark goal %s as NEEDS_HUMAN_REVIEW: no GoalProvider",
            goal_id,
        )
        return

    from myrm_agent_harness.agent.goals.types import GoalStatus

    try:
        await provider.update_status(goal_id, GoalStatus.NEEDS_HUMAN_REVIEW)
    except Exception:
        logger.warning("Could not mark goal %s as NEEDS_HUMAN_REVIEW", goal_id)
        return

    try:
        await _publish_goal_needs_review_notification(session_id, goal_id)
    except Exception:
        logger.exception(
            "Failed to publish goal_needs_review notification for goal %s",
            goal_id,
        )


async def trigger_goal_stream(
    session_id: str,
    goal: Goal,
    *,
    provider: GoalProvider | None = None,
    on_failure: TriggerFailurePolicy = "needs_human_review",
    context: str = "goal stream",
) -> None:
    """Trigger a new agent stream for a dequeued goal.

    Loads full user config (model, search, security) and runs as unattended.
    """
    from app.ai_agents import GeneralAgentParams
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.channel_bridge.config_parsers import (
        extract_fallback_model_configs,
        extract_retrieval_models,
        verify_search_service_available,
    )
    from app.core.channel_bridge.model_resolver import enrich_model_context_window, resolve_model_config
    from app.services.agent.streaming import ai_agent_service_stream

    logger.info(
        "trigger_goal_stream: starting stream for goal %s (%s)",
        goal.goal_id,
        goal.objective[:60],
    )

    user_cfgs = await load_user_configs()
    model_cfg = resolve_model_config(user_cfgs.providers_dict)
    model_cfg = enrich_model_context_window(model_cfg, user_cfgs.providers_dict)
    fallback_model_cfg, fallback_lite_model_cfg = extract_fallback_model_configs(user_cfgs.providers_dict)
    embedding_cfg, reranker_cfg = extract_retrieval_models(user_cfgs.retrieval_dict)

    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig

    GeneralAgentParams.model_rebuild(
        _types_namespace={
            "EmbeddingConfig": EmbeddingConfig,
            "RerankerConfig": RerankerConfig,
        }
    )

    security_config_raw = user_cfgs.security_config_dict or {}
    if not security_config_raw.get("yolo_mode_enabled", False):
        security_config_raw["yolo_mode_enabled"] = True
        security_config_raw["yolo_mode_enabled_at"] = time.time()
        security_config_raw["yolo_mode_timeout"] = None

    params = GeneralAgentParams(
        query=goal.objective,
        chat_id=session_id,
        model_cfg=model_cfg,
        fallback_model_cfg=fallback_model_cfg,
        fallback_lite_model_cfg=fallback_lite_model_cfg,
        search_service_cfg=user_cfgs.search_cfg,
        embedding_config=embedding_cfg,
        reranker_config=reranker_cfg,
        security_config_raw=security_config_raw,
        unattended_mode=True,
        enable_web_search=user_cfgs.search_is_user_configured and await verify_search_service_available(user_cfgs.search_cfg),
    )

    async def _run_stream() -> None:
        try:
            async for _ in ai_agent_service_stream(params):
                pass
        except Exception as e:
            logger.error(
                "Background goal stream failed for goal %s: %s",
                goal.goal_id,
                e,
                exc_info=True,
            )
            await handle_unattended_goal_stream_failure(
                session_id,
                goal.goal_id,
                provider,
                on_failure=on_failure,
                context=context,
            )
        finally:
            _running_goal_tasks.discard(task)

    task = asyncio.create_task(_run_stream())
    _running_goal_tasks.add(task)


async def trigger_goal_stream_with_failure_policy(
    session_id: str,
    goal: Goal,
    provider: GoalProvider | None,
    *,
    on_failure: TriggerFailurePolicy = "needs_human_review",
    context: str = "goal stream",
) -> bool:
    """Trigger unattended stream; apply failure policy on setup or runtime errors."""
    try:
        await trigger_goal_stream(
            session_id,
            goal,
            provider=provider,
            on_failure=on_failure,
            context=context,
        )
        return True
    except Exception as exc:
        logger.error(
            "Failed to trigger %s for goal %s: %s",
            context,
            goal.goal_id,
            exc,
            exc_info=True,
        )
        await handle_unattended_goal_stream_failure(
            session_id,
            goal.goal_id,
            provider,
            on_failure=on_failure,
            context=context,
        )
        return False
