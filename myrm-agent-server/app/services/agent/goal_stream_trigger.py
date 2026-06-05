"""Trigger a new agent stream for a dequeued goal.

Separated from streaming.py to keep the main streaming module under 500 lines.
Called by _try_dequeue_next in goal_learnings.py when the queue has a next goal.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.agent.goals.types import Goal

logger = logging.getLogger(__name__)

_running_goal_tasks: set[asyncio.Task[None]] = set()


async def trigger_goal_stream(session_id: str, goal: Goal) -> None:
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
        finally:
            _running_goal_tasks.discard(task)

    task = asyncio.create_task(_run_stream())
    _running_goal_tasks.add(task)
