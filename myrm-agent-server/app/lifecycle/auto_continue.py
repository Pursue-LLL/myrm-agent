"""Crash auto-continue: resume interrupted normal turns after a restart.

[INPUT]
- app.database.models.chat::InterruptedTurnMarker (POS: 崩溃自动续跑的 write-ahead marker，流开始前写入、正常完成后清理)
- app.services.agent.runtime_context::build_agent_runtime_context (POS: Business-layer helper，为每个 agent 入口注入统一的运行时上下文)
- app.services.agent.streaming::ai_agent_service_stream (POS: Agent 流式服务层，创建 Agent 并经 Gateway 执行，输出 message/message_end 事件)
- app.services.chat.chat_service::ChatService (POS: 聊天业务门面层，为 API、Agent 入口提供统一聊天业务接口)

[OUTPUT]
- auto_continue_interrupted_turns (POS: 启动时扫描 eligible markers 并后台分发重跑)
- _dispatch_auto_continue (POS: 单 marker 重跑 worker，收集 token_economics 持久化消息并清理标记)

[POS]
崩溃自动续跑层。重启后扫描 InterruptedTurnMarker，对 freshness 窗口内且未超 crash-loop 上限的标记
后台重跑被中断的普通回合，将流内 message_end.token_economics 快照作为消息 extra_data 持久化，
与主路径共享消息级成本记账口径；成功/失败均创建 SystemNotification。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.database.models.chat import InterruptedTurnMarker

logger = logging.getLogger(__name__)

_AUTO_CONTINUE_FRESHNESS_MINUTES = 15
_AUTO_CONTINUE_MAX_ATTEMPTS = 2


async def auto_continue_interrupted_turns() -> None:
    """Resume normal turns interrupted by a process crash.

    Scans ``interrupted_turn_markers`` for entries within the freshness window.
    For each qualifying marker, constructs a lightweight agent stream request
    and dispatches it in the background. The marker is cleaned up by the
    normal stream finalization path on success, or incremented and pruned
    on repeated failure (crash-loop breaker).
    """
    try:
        # Check user preference (default: enabled)
        try:
            from app.core.channel_bridge.config_loader import load_user_configs

            configs = await load_user_configs()
            if configs and configs.personal_settings_dict:
                enabled = configs.personal_settings_dict.get("autoContinueInterruptedTurns", True)
                if not enabled:
                    logger.info("[Startup] Auto-continue disabled by user preference")
                    return
        except Exception:
            pass  # Proceed with default (enabled) if config load fails

        from datetime import UTC, datetime, timedelta

        from sqlalchemy import delete, select

        from app.database.models.chat import InterruptedTurnMarker
        from app.platform_utils import get_session_factory

        session_factory = get_session_factory()
        cutoff = datetime.now(UTC) - timedelta(minutes=_AUTO_CONTINUE_FRESHNESS_MINUTES)

        async with session_factory() as db:
            await db.execute(
                delete(InterruptedTurnMarker).where(
                    (InterruptedTurnMarker.created_at < cutoff)
                    | (InterruptedTurnMarker.attempt_count >= _AUTO_CONTINUE_MAX_ATTEMPTS)
                )
            )
            await db.commit()

            result = await db.execute(select(InterruptedTurnMarker))
            markers = result.scalars().all()

        if not markers:
            return

        logger.info("[Startup] Found %d interrupted turn(s) eligible for auto-continue", len(markers))

        for marker in markers:
            asyncio.create_task(_dispatch_auto_continue(marker, session_factory))

    except Exception as e:
        logger.error("[Startup] Auto-continue interrupted turns failed: %s", e, exc_info=True)


async def _dispatch_auto_continue(
    marker: "InterruptedTurnMarker",
    session_factory: "async_sessionmaker[AsyncSession]",
) -> None:
    """Background worker: re-execute one interrupted turn and clean up."""
    from sqlalchemy import delete, update

    from app.database.models.chat import InterruptedTurnMarker

    try:
        # Increment attempt count first (crash-loop protection)
        async with session_factory() as db:
            await db.execute(
                update(InterruptedTurnMarker)
                .where(InterruptedTurnMarker.id == marker.id)
                .values(attempt_count=marker.attempt_count + 1)
            )
            await db.commit()

        if not marker.serialized_params:
            logger.warning("Auto-continue skipped for chat %s: missing params", marker.chat_id)
            return

        from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

        from app.ai_agents import GeneralAgentParams
        from app.services.agent.execution_cache.types import ExecutionMode
        from app.services.agent.runtime_context import build_agent_runtime_context
        from app.services.agent.streaming import ai_agent_service_stream
        from app.services.agent.streaming_support.stream_collector_helpers import (
            string_keyed_dict,
        )
        from app.services.chat.chat_service import ChatService

        params = GeneralAgentParams.model_validate(marker.serialized_params)
        params.message_id = f"auto_continue_{marker.id}"

        if not params.model_cfg:
            logger.warning("Auto-continue skipped for chat %s: missing model_cfg", marker.chat_id)
            return

        if marker.chat_id:
            params.chat_history = await ChatService.load_web_chat_history(marker.chat_id)

        token = CancellationToken(request_id=params.message_id or marker.id)

        logger.info("[Auto-continue] Resuming interrupted turn for chat: %s", marker.chat_id)

        runtime_context = await build_agent_runtime_context(
            execution_mode=ExecutionMode.POOLED,
        )

        collected_parts: list[str] = []
        token_economics: dict[str, object] | None = None
        stream = ai_agent_service_stream(
            params=params,
            cancel_token=token,
            extra_context=runtime_context,
        )
        async for chunk in stream:
            if not isinstance(chunk, dict):
                continue
            event_type = chunk.get("type")
            if event_type == "message" and isinstance(chunk.get("data"), str):
                collected_parts.append(chunk["data"])
            elif event_type == "message_end":
                # Keep the persisted snapshot aligned with the canonical path:
                # stream_finalize extracts token_economics from this same event.
                token_economics = string_keyed_dict(chunk.get("token_economics"))

        if collected_parts and marker.chat_id:
            extra_data: dict[str, object] | None = None
            if token_economics:
                extra_data = {"tokenEconomics": token_economics}
            await ChatService.persist_assistant_message_safe(
                marker.chat_id,
                "".join(collected_parts),
                timezone=params.timezone,
                request_message_id=params.message_id,
                extra_data=extra_data,
            )

        logger.info("[Auto-continue] Completed for chat: %s", marker.chat_id)

        # Notify user
        from app.services.infra.system_notification import SystemNotificationService

        await SystemNotificationService.create_notification(
            title="Interrupted Turn Resumed",
            message="A conversation was automatically resumed after a restart.",
            type="success",
            source="auto_continue",
            meta_data={"chat_id": marker.chat_id, "action_url": f"/{marker.chat_id}"},
        )

    except Exception as e:
        logger.error("[Auto-continue] Failed for chat %s: %s", marker.chat_id, e, exc_info=True)
        try:
            from app.services.infra.system_notification import SystemNotificationService

            await SystemNotificationService.create_notification(
                title="Turn Resume Failed",
                message="Could not automatically resume an interrupted conversation. Please retry.",
                type="error",
                source="auto_continue",
                meta_data={"chat_id": marker.chat_id, "action_url": f"/{marker.chat_id}"},
            )
        except Exception as notif_err:
            logger.error("Failed to create auto-continue failure notification: %s", notif_err)
    finally:
        # Cleanup marker (stream_finalize may have already done this on success)
        try:
            async with session_factory() as db:
                await db.execute(delete(InterruptedTurnMarker).where(InterruptedTurnMarker.id == marker.id))
                await db.commit()
        except Exception as cleanup_err:
            logger.debug("Auto-continue marker cleanup: %s", cleanup_err)
