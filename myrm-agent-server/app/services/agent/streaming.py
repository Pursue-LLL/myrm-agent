"""Agent streaming services.

Bridges Agent/Orchestrator → AgentGateway → SSE output.

[INPUT]
- ai_agents::AgentFactory, GeneralAgentParams
- services.agent.gateway::get_agent_gateway
- app.services.approvals.registry::ApprovalRegistry (POS: 统一的拦截审批注册与唤醒中枢)
- myrm_agent_harness.toolkits.interaction::AskQuestionInput (POS: 深研究澄清表单结构输入)

[OUTPUT]
- ai_agent_service_stream: General Agent SSE stream (budget_blocked semantic code; progress.started without UI copy)
- ai_deep_research_service_stream: Deep Research SSE stream
- ClarificationWaiter: In-process suspend/resume for Deep Research clarification
- swarm_fission_resume::stream_with_swarm_fission_resume (POS: Swarm Fission Yield-Resume server orchestration)

[POS]
Agent 流式服务层。创建 Agent/Orchestrator，通过 Gateway 执行
（并发控制 + 超时），将事件转为 SSE 格式。
Gateway 异常（Queue/Execution Timeout）向上传播给 API 层处理。
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterable
from typing import TYPE_CHECKING

from app.ai_agents import AgentFactory, GeneralAgentParams
from app.core.utils.chat_utils import convert_chat_history
from app.services.agent.gateway import get_agent_gateway

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import BaseMessage
    from langchain_core.tools import BaseTool
    from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
    from myrm_agent_harness.utils.runtime.steering import SteeringToken

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Clarification waiter — in-process suspend/resume for Deep Research
# ---------------------------------------------------------------------------

_clarification_waiters: dict[str, "ClarificationWaiter"] = {}

CLARIFICATION_TIMEOUT_SECONDS = 300
ClarificationAnswer = str | list[str] | dict[str, str | list[str]]


class ClarificationWaiter:
    """Holds an asyncio.Event so the orchestrator can await user clarification.

    Lifecycle: created when orchestrator enters CLARIFY phase,
    resolved when user POSTs a response, auto-expired after timeout.
    """

    __slots__ = ("_event", "_answer", "message_id")

    def __init__(self, message_id: str) -> None:
        self.message_id = message_id
        self._event = asyncio.Event()
        self._answer: ClarificationAnswer | None = None

    async def wait_for_answer(self) -> ClarificationAnswer | None:
        """Block until the user responds or timeout."""
        try:
            await asyncio.wait_for(self._event.wait(), timeout=CLARIFICATION_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.info("Clarification timed out for message_id=%s", self.message_id)
            return None
        finally:
            _clarification_waiters.pop(self.message_id, None)
        return self._answer

    @property
    def is_resolved(self) -> bool:
        return self._event.is_set()

    def resolve(self, answer: ClarificationAnswer) -> None:
        self._answer = answer
        self._event.set()

    @staticmethod
    def register(message_id: str) -> "ClarificationWaiter":
        waiter = ClarificationWaiter(message_id)
        _clarification_waiters[message_id] = waiter
        return waiter

    @staticmethod
    def get(message_id: str) -> "ClarificationWaiter | None":
        return _clarification_waiters.get(message_id)


async def ai_agent_service_stream(
    params: GeneralAgentParams,
    cancel_token: "CancellationToken | None" = None,
    steering_token: "SteeringToken | None" = None,
    extra_context: dict[str, object] | None = None,
) -> AsyncIterable[dict[str, object]]:
    """Execute General Agent with gateway lifecycle management.

    Gateway exceptions (AgentQueueTimeout, AgentExecutionTimeout)
    propagate to the caller for HTTP-level handling.
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

    reset_session_budget(chat_id=params.chat_id)

    agent = AgentFactory.create_general_agent(params)
    try:
        chat_history = await convert_chat_history(params.chat_history)

        async def _open_stream(
            query_input: object,
        ) -> AsyncGenerator[dict[str, object], None]:
            async for event in agent.process_stream(
                query=query_input,
                chat_history=chat_history,
                message_id=params.message_id,
                chat_id=params.chat_id,
                cancel_token=cancel_token,
                steering_token=steering_token,
                timezone=params.timezone,
                force_delegate_agent=params.force_delegate_agent,
                context=extra_context,
            ):
                if isinstance(event, dict):
                    yield event
                else:
                    yield {"payload": event}

        from app.services.agent.fission_config import max_parallel_from_engine_params
        from app.services.agent.swarm_fission_resume import (
            stream_with_swarm_fission_resume,
        )

        fission_concurrency = max_parallel_from_engine_params(params.engine_params)
        raw_stream = stream_with_swarm_fission_resume(
            agent,
            params.query,
            _open_stream,
            max_concurrent=fission_concurrency,
        )

        goal_active = False
        if extra_context and extra_context.get("goal_provider") and params.chat_id:
            goal_provider = extra_context["goal_provider"]
            active_goal = await goal_provider.get_active_goal(params.chat_id)
            goal_active = active_goal is not None

        gateway = get_agent_gateway()
        async for event in gateway.execute_stream(
            raw_stream,
            agent_type="general",
            session_id=params.chat_id,
            agent_instance=agent,
            goal_active=goal_active,
            fission_active=fission_concurrency > 1,
        ):
            if cancel_token and cancel_token.is_cancelled:
                logger.warning("Agent stream cancelled: message_id=%s", params.message_id)
                break

            # Intercept APPROVAL_REQUIRED events to persist to DB
            event_type = getattr(event, "type", None) if not isinstance(event, dict) else event.get("type")
            if event_type == "approval_required":
                from app.services.approvals.registry import ApprovalRegistry

                approval_data = getattr(event, "data", {}) if not isinstance(event, dict) else event.get("data", {})
                if isinstance(approval_data, dict):
                    thread_id = params.chat_id or params.message_id

                    action_type = approval_data.get("action_type", "unknown")

                    try:
                        approval_payload = approval_data.get("payload", {})
                        timeout_seconds = approval_payload.get("approval_timeout_seconds")
                        expires_at = None
                        if timeout_seconds:
                            from datetime import datetime, timedelta, timezone

                            expires_at = datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)

                        record = await ApprovalRegistry.create_approval(
                            agent_id=params.agent_id or "default",
                            chat_id=params.chat_id,
                            thread_id=thread_id,
                            action_type=action_type,
                            payload=approval_payload,
                            reason=approval_data.get("reason"),
                            severity=approval_data.get("severity", "warning"),
                            status="PENDING",
                            expires_at=expires_at,
                        )
                        # Enrich event with approval_id so frontend knows which ID to resolve

                        # Fix for AgentStreamEvent object not supporting item assignment
                        if hasattr(event, "to_dict"):
                            event_dict = event.to_dict()
                            event_dict["data"]["approval_id"] = record.id
                            event = event_dict
                        elif hasattr(event, "model_dump"):
                            event_dict = event.model_dump()
                            event_dict["data"]["approval_id"] = record.id
                            event = event_dict
                        elif isinstance(event, dict):
                            approval_data["approval_id"] = record.id
                            event["data"] = approval_data
                    except Exception as e:
                        logger.error("Failed to persist approval: %s", e)

            # Map event type to mascot status and inject
            try:
                from app.services.mascot import MascotStateMapper

                raw_event_type = ""
                payload = {}
                if isinstance(event, dict):
                    raw_event_type = event.get("type", "")
                    payload = event.get("data", {}) or {}
                elif hasattr(event, "type"):
                    raw_event_type = getattr(event, "type", "")
                    payload = getattr(event, "data", {}) or {}

                mascot_status = MascotStateMapper.map_event_to_mascot_state(raw_event_type, payload)

                if isinstance(event, dict):
                    event["mascot_status"] = mascot_status.value
                elif hasattr(event, "to_dict"):
                    event_dict = event.to_dict()
                    event_dict["mascot_status"] = mascot_status.value
                    event = event_dict
                elif hasattr(event, "model_dump"):
                    event_dict = event.model_dump()
                    event_dict["mascot_status"] = mascot_status.value
                    event = event_dict
            except Exception as ex:
                logger.warning("Failed to inject mascot status to event: %s", ex)

            # Broadcast DAG state updates if present
            try:
                event_type = getattr(event, "type", None) if not isinstance(event, dict) else event.get("type")
                if event_type == "dag_state_update":
                    (getattr(event, "data", {}) if not isinstance(event, dict) else event.get("data", {}))
                    # We yield it so the SSE connection can push it to the client
                    # The frontend should listen for this event type
            except Exception as ex:
                logger.warning("Failed to process dag state update: %s", ex)

            yield event
    finally:
        await agent.close()


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
    from myrm_agent_harness.agent.streaming.types import AgentEventType
    from myrm_agent_harness.toolkits.interaction import AskQuestionInput

    _SENTINEL = object()
    _HEARTBEAT_INTERVAL = 15  # seconds — well under typical proxy idle timeouts

    event_queue: asyncio.Queue[dict[str, object] | object] = asyncio.Queue()

    async def _on_clarify(_form: AskQuestionInput) -> ClarificationAnswer | None:
        """Suspend the orchestrator while the user answers a clarification question.

        The SSE MESSAGE event (with metadata.phase='clarify') has already been
        yielded by the orchestrator before this callback is invoked (including
        structured ``form`` in metadata when applicable). We register a waiter and
        block until the user POSTs to /agents/clarify-response.
        During the wait, a heartbeat task keeps the SSE connection alive.
        """
        waiter = ClarificationWaiter.register(message_id)
        logger.info("[deep-research] Clarification waiting: message_id=%s", message_id)

        async def _heartbeat() -> None:
            while not waiter.is_resolved:
                await asyncio.sleep(_HEARTBEAT_INTERVAL)
                if not waiter.is_resolved:
                    await event_queue.put(
                        {
                            "type": AgentEventType.STATUS.value,
                            "messageId": message_id,
                            "data": {"phase": "clarify", "status": "waiting"},
                        }
                    )

        heartbeat_task = asyncio.create_task(_heartbeat())
        try:
            answer = await waiter.wait_for_answer()
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

        await event_queue.put(
            {
                "type": AgentEventType.STATUS.value,
                "messageId": message_id,
                "data": {
                    "phase": "clarify",
                    "status": "resolved",
                    "skipped": answer is None or answer == "",
                },
            }
        )
        return answer

    orch = DeepResearchOrchestrator(
        llm=llm,
        parent_tools=parent_tools or [],
        cancel_token=cancel_token,
        context=context or {},
        research_agent_llm=research_agent_llm,
        on_clarify=_on_clarify,
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

        async for event in gateway.execute_stream(
            _raw_stream(),
            agent_type="deep_research",
            session_id=session_id_val,
            agent_instance=agent_instance,
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
        _clarification_waiters.pop(message_id, None)

    if producer_error is not None:
        raise producer_error
