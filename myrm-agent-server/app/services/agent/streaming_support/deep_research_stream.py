"""Deep Research SSE stream.

[INPUT]
- services.agent.gateway::get_agent_gateway (POS: 统一的 Agent 执行网关，并发控制与超时)
- services.agent.streaming::PhaseWaiter (POS: 通用阶段暂停/恢复门控，Clarification + Plan Confirmation HITL)
- myrm_agent_harness.agent.deep_research::DeepResearchOrchestrator (POS: 深度研究编排器)

[OUTPUT]
- ai_deep_research_service_stream: Deep Research SSE stream (clarify and plan-confirm phases suspend on PhaseWaiter
  while heartbeats keep the connection open; budget_blocked semantic code; progress.started without UI copy)

[POS]
Deep Research 流式桥接层。创建 DeepResearchOrchestrator，把它的事件经 Gateway 转为 SSE，并把澄清与计划确认两个
阶段接到 PhaseWaiter 上。Gateway 异常（Queue/Execution Timeout）向上传播给 API 层处理。
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterable
from typing import TYPE_CHECKING

from app.services.agent.gateway import get_agent_gateway
from app.services.agent.streaming import PhaseAnswer, PhaseWaiter

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import BaseMessage
    from langchain_core.tools import BaseTool
    from myrm_agent_harness.agent.deep_research.helpers import DeepResearchResult
    from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

logger = logging.getLogger(__name__)


async def ai_deep_research_service_stream(
    llm: "BaseChatModel",
    query: str,
    message_id: str,
    user_id: str = "",
    chat_history: "list[BaseMessage] | None" = None,
    parent_tools: "list[BaseTool] | None" = None,
    cancel_token: "CancellationToken | None" = None,
    context: dict[str, object] | None = None,
    research_agent_llm: "BaseChatModel | None" = None,
    on_report_ready: "Callable[[DeepResearchResult], Awaitable[None]] | None" = None,
    on_explore: "Callable[[str], Awaitable[str | None]] | None" = None,
) -> AsyncIterable[dict[str, object]]:
    """Execute Deep Research Orchestrator with gateway lifecycle management.

    Gateway exceptions propagate to the caller for HTTP-level handling.
    """
    from app.services.budget.enforcer import (
        reset_session_budget,
        should_block_execution,
    )

    if await should_block_execution():
        yield {
            "type": "message",
            "data": "",
        }
        yield {
            "type": "message_end",
            "usage": {},
            "completion_status": "budget_blocked",
        }
        return

    yield {
        "type": "progress",
        "data": {
            "status": "started",
            "progress_pct": 5,
        },
    }

    session_id = str(context.get("session_id", "")) if context else None
    reset_session_budget(chat_id=session_id or None)

    from myrm_agent_harness.agent.deep_research import DeepResearchOrchestrator
    from myrm_agent_harness.agent.meta_tools.clarification import AskQuestionInput
    from myrm_agent_harness.api import AgentEventType

    _SENTINEL = object()
    _HEARTBEAT_INTERVAL = 15  # seconds — well under typical proxy idle timeouts

    event_queue: asyncio.Queue[dict[str, object] | object] = asyncio.Queue()

    async def _wait_with_heartbeat(waiter: PhaseWaiter, phase: str) -> PhaseAnswer:
        """Wait for a PhaseWaiter while emitting SSE heartbeats."""

        async def _heartbeat() -> None:
            while not waiter.is_resolved:
                await asyncio.sleep(_HEARTBEAT_INTERVAL)
                if not waiter.is_resolved:
                    await event_queue.put(
                        {
                            "type": AgentEventType.STATUS.value,
                            "messageId": message_id,
                            "data": {"phase": phase, "status": "waiting"},
                        }
                    )

        heartbeat_task = asyncio.create_task(_heartbeat())
        try:
            return await waiter.wait_for_answer()
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _on_clarify(_form: AskQuestionInput) -> PhaseAnswer:
        """Suspend the orchestrator while the user answers a clarification question."""
        waiter = PhaseWaiter.register(message_id)
        logger.info("[deep-research] Clarification waiting: message_id=%s", message_id)

        answer = await _wait_with_heartbeat(waiter, "clarify")

        await event_queue.put(
            {
                "type": AgentEventType.STATUS.value,
                "messageId": message_id,
                "data": {
                    "phase": "clarify",
                    "status": "resolved",
                    "skipped": answer is None or answer == "",
                    # The clarify endpoint requires a body answer, so None only comes from the timeout.
                    "answerRecord": {"by": "timeout", "value": {}} if answer is None else {"by": "user", "value": answer},
                },
            }
        )
        return answer

    async def _on_plan_ready(plan: str) -> str | None:
        """Suspend the orchestrator so the user can review/edit the research plan."""
        plan_key = f"plan:{message_id}"
        waiter = PhaseWaiter.register(plan_key)
        logger.info("[deep-research] Plan confirmation waiting: message_id=%s", message_id)

        await event_queue.put(
            {
                "type": AgentEventType.STATUS.value,
                "messageId": message_id,
                "data": {
                    "phase": "plan_confirm",
                    "status": "waiting",
                    "plan": plan,
                },
            }
        )

        answer = await _wait_with_heartbeat(waiter, "plan_confirm")

        modified_plan: str | None = None
        if isinstance(answer, str) and answer.strip():
            modified_plan = answer.strip()

        await event_queue.put(
            {
                "type": AgentEventType.STATUS.value,
                "messageId": message_id,
                "data": {
                    "phase": "plan_confirm",
                    "status": "resolved",
                    "modified": modified_plan is not None,
                },
            }
        )
        return modified_plan

    orch = DeepResearchOrchestrator(
        llm=llm,
        parent_tools=parent_tools or [],
        cancel_token=cancel_token,
        context=context or {},
        research_agent_llm=research_agent_llm,
        on_clarify=_on_clarify,
        on_plan_ready=_on_plan_ready,
        on_explore=on_explore,
        on_report_ready=on_report_ready,
    )

    producer_error: BaseException | None = None

    async def _producer() -> None:
        """Run orchestrator and push events into the queue."""
        nonlocal producer_error
        try:
            async for event in orch.run(
                query=query,
                chat_history=chat_history,
                message_id=message_id,
            ):
                await event_queue.put(event)
        except BaseException as exc:
            producer_error = exc
        finally:
            await event_queue.put(_SENTINEL)

    async def _raw_stream() -> AsyncGenerator[dict[str, object], None]:
        """Consume from the queue, yielding events until sentinel."""
        while True:
            event = await event_queue.get()
            if event is _SENTINEL:
                break
            if isinstance(event, dict):
                yield {str(k): v for k, v in event.items()}
            else:
                yield {"payload": event}

    producer_task = asyncio.create_task(_producer())
    try:
        gateway = get_agent_gateway()
        raw_session: object | None = context.get("session_id") if context else None
        session_id_val: str | None = raw_session if isinstance(raw_session, str) else None

        # Determine agent_instance for deep research if possible
        # DeepResearchOrchestrator might not be a BaseAgent directly,
        # but if it exposes its main agent, we could pass it.
        # For now we pass None or orch if it inherits from BaseAgent.
        agent_instance = orch if hasattr(orch, "subagent_manager") else getattr(orch, "_research_agent", None)

        raw_agent_id: object | None = context.get("agent_id") if context else None
        dr_agent_id: str | None = raw_agent_id if isinstance(raw_agent_id, str) else None

        async for event in gateway.execute_stream(
            _raw_stream(),
            agent_type="deep_research",
            session_id=session_id_val,
            agent_instance=agent_instance,
            active_message_id=message_id,
            agent_id=dr_agent_id,
        ):
            if cancel_token and cancel_token.is_cancelled:
                logger.warning("Deep research stream cancelled: message_id=%s", message_id)
                break
            yield event
    finally:
        producer_task.cancel()
        try:
            await producer_task
        except asyncio.CancelledError:
            pass
        PhaseWaiter.discard(message_id)
        PhaseWaiter.discard(f"plan:{message_id}")

    if producer_error is not None:
        raise producer_error
