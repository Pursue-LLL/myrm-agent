"""Pump generated SSE chunks into the global stream buffer.

[INPUT]
- app.services.agent.stream_session.stream_chunks::generate_cancellable_stream (POS: Agent 流式 SSE chunk 编排：凭据注入、三轨 gap 预检、Vision fallback，委托 loop/finalize)
- app.services.agent.stream_session.stream_session_types::AgentStreamSession (POS: 单回合会话状态)
- app.services.agent.stream_session.pre_reply_compact_sse (POS: Web-only SSE wiring for idle pre-reply compaction. Reuses frontend context_compaction progress steps)
- app.services.agent.streaming_support.sse_helpers::error_sse (POS: SSE 事件辅助层。提供 SSE 事件解析、错误格式化，以及审批/澄清 HITL 超时后台 auto-resume 调度)
- app.services.agent.streaming_support.multiplexer::WorkspaceMultiplexer (POS: Workspace SSE Multiplexer for multi-tab support)
- app.schemas.streaming::SSEEnvelope (POS: 业务层 SSE 序列化防腐层。保证发送给前端的每个 chunk 符合统一类型)
- app.services.project.orchestrator::project_orchestrator (POS: 项目并发控制。确保同一个项目的多个 Agent 不会并发修改工作区文件)
- app.services.agent.gateway::get_agent_gateway (POS: Agent 执行网关。并发控制、内存压力熔断、优雅排空、超时保护和可观测性)
- app.services.infra.system_notification::SystemNotificationService (POS: System notification persistence service for API/business layers)
- myrm_agent_harness.agent.streaming.stream_buffer::ResilientStreamBuffer (POS: Harness engine-layer SSE reconnect replay buffer)
- myrm_agent_harness.utils.runtime.cancellation::CancellationToken (POS: Cancellation token mechanism. Provides request-level cancellation state management)

[OUTPUT]
- pump_to_buffer: run a turn's SSE stream into its replay buffer and the workspace multiplexer, serialize turns per project, and notify the user when a long-running turn ends after the client left

[POS]
Background pump of an E1 turn: owns the turn from the project turn-lock wait to the delayed buffer cleanup.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.services.agent.stream_session.stream_chunks import generate_cancellable_stream
from app.services.agent.stream_session.stream_session_types import AgentStreamSession
from app.services.agent.streaming_support.sse_helpers import error_sse

if TYPE_CHECKING:
    from myrm_agent_harness.agent.streaming.stream_buffer import ResilientStreamBuffer
    from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

    from app.services.project.orchestrator import ProjectOrchestrator

logger = logging.getLogger(__name__)


async def _acquire_guarded(
    orch: ProjectOrchestrator,
    project_id: str,
    cancel_token: CancellationToken,
) -> None:
    """Acquire the project turn lock while reacting to user cancel/disconnect.

    ``asyncio.Lock.acquire()`` does not observe the request cancellation token,
    so a turn queued behind another agent could stay blocked for minutes after
    the user cancels. Poll in short slices and abort as soon as the token fires
    (1s worst-case cancellation latency, lock ownership is safe on Python 3.12+).
    """
    while True:
        if cancel_token.is_cancelled:
            raise asyncio.CancelledError
        try:
            await asyncio.wait_for(orch.acquire(project_id), timeout=1.0)
            return
        except asyncio.TimeoutError:
            continue


async def pump_to_buffer(session: AgentStreamSession, buffer: ResilientStreamBuffer) -> None:
    from app.schemas.streaming import SSEEnvelope
    from app.services.agent.stream_session.pre_reply_compact_sse import (
        append_pre_reply_compact_sse,
    )
    from app.services.project.orchestrator import project_orchestrator

    message_id = session.request.message_id

    if not session.pre_reply_compact_sse_sent:
        await append_pre_reply_compact_sse(
            buffer,
            message_id,
            session.pre_reply_compact_result,
        )

    project_id = getattr(session.params, "project_id", None)

    if project_id and project_orchestrator.is_locked(project_id):
        waiting_msg = SSEEnvelope.from_any(
            {
                "type": "status",
                "messageId": message_id,
                "step_key": "waiting_for_turn",
                "status": "waiting",
                "data": {"message": "Waiting for other agents in the project to finish..."},
            }
        ).to_sse_chunk()
        await buffer.append(waiting_msg)

    stream_had_error = False
    lock_acquired = False
    try:
        if project_id:
            await _acquire_guarded(
                project_orchestrator,
                project_id,
                session.cancel_token,
            )
            lock_acquired = True

            cleared_msg = SSEEnvelope.from_any(
                {
                    "type": "status",
                    "messageId": message_id,
                    "step_key": "waiting_for_turn_clear",
                    "status": "success",
                }
            ).to_sse_chunk()
            await buffer.append(cleared_msg)

        async for chunk in generate_cancellable_stream(session):
            if chunk.strip():
                if not stream_had_error and '"type": "error"' in chunk:
                    stream_had_error = True
                await buffer.append(chunk)
                from app.services.agent.streaming_support.multiplexer import (
                    WorkspaceMultiplexer,
                )

                await WorkspaceMultiplexer.get().publish(
                    chat_id=session.request.chat_id,
                    message_id=message_id,
                    chunk=chunk,
                )
    except asyncio.CancelledError:
        pass
    except Exception as e:
        stream_had_error = True
        logger.error("Error pumping stream to buffer: %s", e, exc_info=True)
        await buffer.append(error_sse("Stream interrupted", message_id))
    finally:
        if project_id and lock_acquired:
            project_orchestrator.release(project_id)
        if session.request.chat_id:
            from app.services.agent.gateway import get_agent_gateway

            get_agent_gateway().release_if_reserved_only(session.request.chat_id)
        await buffer.end_stream()

        # A long-running turn keeps going after its client left; tell the user once it ends.
        try:
            if session.is_long_running_task and not session.cancel_token.is_cancelled:
                if await session.http_request.is_disconnected():
                    from app.services.infra.system_notification import (
                        SystemNotificationService,
                    )

                    if stream_had_error or session.had_fatal_error:
                        await SystemNotificationService.create_notification(
                            title="Task Failed",
                            message="Your background task encountered an error and could not complete. Please check the chat for details.",
                            type="error",
                            source="offline_guardian",
                            meta_data={
                                "chat_id": session.request.chat_id,
                                "message_id": message_id,
                                "action_url": f"/{session.request.chat_id}",
                            },
                        )
                        logger.info(
                            "Offline Guardian error notification sent for: %s",
                            message_id,
                        )
                    else:
                        await SystemNotificationService.create_notification(
                            title="Task Completed",
                            message="Your background task has successfully completed. You can view the results in the chat.",
                            type="success",
                            source="offline_guardian",
                            meta_data={
                                "chat_id": session.request.chat_id,
                                "message_id": message_id,
                                "action_url": f"/{session.request.chat_id}",
                            },
                        )
                        logger.info(
                            "Offline Guardian notification sent for: %s",
                            message_id,
                        )
        except Exception as e:
            logger.error("Offline Guardian notification error: %s", e)

        async def _delayed_remove() -> None:
            try:
                await asyncio.sleep(300)
                await session.registry.remove(message_id)
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(
            _delayed_remove(),
            name=f"buffer_cleanup_{message_id}",
        )
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() and t.exception() else None)
