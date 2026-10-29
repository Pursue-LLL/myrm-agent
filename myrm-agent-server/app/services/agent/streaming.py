"""Agent streaming services.

Bridges Agent/Orchestrator → AgentGateway → SSE output.

[INPUT]
- ai_agents::AgentFactory, GeneralAgentParams
- services.agent.gateway::get_agent_gateway
- services.agent.streaming_support.takeover_live_assist::inject_takeover_live_assist_url (POS: browser takeover 事件的签名 live-assist 链接注入)
- app.services.approvals.registry::ApprovalRegistry (POS: 统一的拦截审批注册与唤醒中枢)

[OUTPUT]
- ai_agent_service_stream: General Agent SSE stream (budget_blocked semantic code; progress.started without UI copy)
- PhaseWaiter: Generic in-process suspend/resume for Deep Research phases (clarification, plan confirmation); the Deep Research stream in streaming_support/deep_research_stream.py waits on it
- swarm_fission_resume::stream_with_swarm_fission_resume (POS: Swarm Fission Yield-Resume server orchestration)

[POS]
Agent 流式服务层。创建 Agent/Orchestrator，通过 Gateway 执行
（并发控制 + 超时），将事件转为 SSE 格式。
Gateway 异常（Queue/Execution Timeout）向上传播给 API 层处理。
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterable
from typing import TYPE_CHECKING, cast

from app.ai_agents import AgentFactory, GeneralAgentParams
from app.core.utils.chat_utils import convert_chat_history
from app.services.agent.approval_payload import extract_approval_registry_payload, is_tool_stuck_pause
from app.services.agent.gateway import get_agent_gateway
from app.services.agent.streaming_support.takeover_live_assist import (
    TakeoverLiveAssistCache,
    inject_takeover_live_assist_url,
)

if TYPE_CHECKING:
    from myrm_agent_harness.agent.goals.protocols import GoalProvider
    from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
    from myrm_agent_harness.utils.runtime.steering import SteeringToken

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PhaseWaiter — generic in-process suspend/resume for Deep Research phases
# ---------------------------------------------------------------------------

PhaseAnswer = str | list[str] | dict[str, str | list[str]] | None

PHASE_TIMEOUT_SECONDS = 300

_phase_waiters: dict[str, "PhaseWaiter"] = {}


class PhaseWaiter:
    """Generic suspend/resume gate for Deep Research orchestrator phases.

    Used by both Clarification and Plan Confirmation to pause the
    orchestrator while the user provides input via a POST endpoint.
    Auto-expires after PHASE_TIMEOUT_SECONDS.
    """

    __slots__ = ("_event", "_answer", "key")

    def __init__(self, key: str) -> None:
        self.key = key
        self._event = asyncio.Event()
        self._answer: PhaseAnswer = None

    async def wait_for_answer(self) -> PhaseAnswer:
        """Block until the user responds or timeout."""
        try:
            await asyncio.wait_for(self._event.wait(), timeout=PHASE_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.info("PhaseWaiter timed out: key=%s", self.key)
            return None
        finally:
            _phase_waiters.pop(self.key, None)
        return self._answer

    @property
    def is_resolved(self) -> bool:
        return self._event.is_set()

    def resolve(self, answer: PhaseAnswer) -> None:
        self._answer = answer
        self._event.set()

    @staticmethod
    def register(key: str) -> "PhaseWaiter":
        waiter = PhaseWaiter(key)
        _phase_waiters[key] = waiter
        return waiter

    @staticmethod
    def get(key: str) -> "PhaseWaiter | None":
        return _phase_waiters.get(key)

    @staticmethod
    def discard(key: str) -> None:
        _phase_waiters.pop(key, None)


async def ai_agent_service_stream(
    params: GeneralAgentParams,
    cancel_token: "CancellationToken | None" = None,
    steering_token: "SteeringToken | None" = None,
    extra_context: dict[str, object] | None = None,
) -> AsyncIterable[dict[str, object]]:
    """Execute General Agent with gateway lifecycle management.

    Gateway exceptions (AgentQueueTimeout, AgentExecutionTimeout)
    propagate to the caller for HTTP-level handling.

    The stream runs inside the turn's model-call memo scope, so an interrupted turn that is
    replayed does not pay for the model twice. The scope is absent unless the caller set a
    turn identity and a ledger path, and then the behaviour is unchanged.
    """
    from app.services.agent.memo_scope import memo_scoped_stream

    async for chunk in memo_scoped_stream(
        _ai_agent_service_stream_inner(
            params,
            cancel_token=cancel_token,
            steering_token=steering_token,
            extra_context=extra_context,
        ),
        params,
    ):
        yield chunk


async def _ai_agent_service_stream_inner(
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
                force_external_agent=params.force_external_agent,
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
            goal_provider = cast("GoalProvider", extra_context["goal_provider"])
            active_goal = await goal_provider.get_active_goal(params.chat_id)
            goal_active = active_goal is not None

        gateway = get_agent_gateway()
        takeover_live_assist_cache: TakeoverLiveAssistCache | None = None
        _pending_attention = False
        async for event in gateway.execute_stream(
            raw_stream,
            agent_type="general",
            session_id=params.chat_id,
            agent_instance=agent,
            active_message_id=params.message_id,
            goal_active=goal_active,
            fission_active=fission_concurrency > 1,
            agent_id=params.agent_id,
        ):
            if cancel_token and cancel_token.is_cancelled:
                logger.warning("Agent stream cancelled: message_id=%s", params.message_id)
                break

            try:
                injected, takeover_cache = await inject_takeover_live_assist_url(
                    event,
                    chat_id=params.chat_id,
                    message_id=params.message_id,
                    cached=takeover_live_assist_cache,
                )
                # Only a takeover event is rewritten, and into a dict; any other event comes back as it went in.
                if isinstance(injected, dict):
                    event = injected
                takeover_live_assist_cache = takeover_cache
            except Exception as ex:
                logger.warning("Failed to inject takeover live assist URL: %s", ex)

            # Intercept APPROVAL_REQUIRED events to persist to DB
            event_type = getattr(event, "type", None) if not isinstance(event, dict) else event.get("type")
            interrupt_data = getattr(event, "data", {}) if not isinstance(event, dict) else event.get("data", {})
            # A loop guard pause is no approval: nothing waits on an answer, so it gets no record and no attention.
            awaits_answer = event_type in (
                "approval_required",
                "tool_approval_request",
                "clarification_required",
            ) and not is_tool_stuck_pause(interrupt_data)
            if awaits_answer:
                _pending_attention = True
            if awaits_answer and event_type == "approval_required":
                from app.services.approvals.registry import ApprovalRegistry

                approval_data = interrupt_data
                if isinstance(approval_data, dict):
                    thread_id = params.chat_id or params.message_id

                    action_type = approval_data.get("action_type", "unknown")

                    try:
                        approval_payload = extract_approval_registry_payload(approval_data)
                        if params.message_id:
                            approval_payload = {
                                **approval_payload,
                                "messageId": params.message_id,
                            }
                        timeout_seconds = approval_payload.get("approval_timeout_seconds")
                        expires_at = None
                        if isinstance(timeout_seconds, int | float) and timeout_seconds:
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
                        if params.message_id:
                            approval_data["messageId"] = params.message_id
                        if hasattr(event, "to_dict"):
                            event_dict = event.to_dict()
                            event_dict["data"]["approval_id"] = record.id
                            if params.message_id:
                                event_dict["data"]["messageId"] = params.message_id
                            event = event_dict
                        elif hasattr(event, "model_dump"):
                            event_dict = event.model_dump()
                            event_dict["data"]["approval_id"] = record.id
                            if params.message_id:
                                event_dict["data"]["messageId"] = params.message_id
                            event = event_dict
                        elif isinstance(event, dict):
                            approval_data["approval_id"] = record.id
                            event["data"] = approval_data
                    except Exception as e:
                        logger.error("Failed to persist approval: %s", e)

            # Map event type to mascot status and inject
            try:
                from app.services.mascot import MascotStateMapper

                raw_event_type: object = ""
                raw_payload: object = {}
                if isinstance(event, dict):
                    raw_event_type = event.get("type", "")
                    raw_payload = event.get("data", {}) or {}
                elif hasattr(event, "type"):
                    raw_event_type = getattr(event, "type", "")
                    raw_payload = getattr(event, "data", {}) or {}

                mascot_status = MascotStateMapper.map_event_to_mascot_state(
                    raw_event_type if isinstance(raw_event_type, str) else "",
                    raw_payload if isinstance(raw_payload, dict) else {},
                )

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
                logger.warning("Failed to process event state update: %s", ex)

            yield event
    except Exception:
        if hasattr(agent, "_browser_session") and agent._browser_session is not None:
            agent._browser_session.mark_task_failure()
        raise
    finally:
        from app.services.agent.execution_cache import finalize_agent_session

        await finalize_agent_session(
            agent,
            chat_id=params.chat_id,
            agent_id=params.agent_id,
            extra_context=extra_context,
        )
        if _pending_attention and params.chat_id:
            from app.services.agent.streaming_support.multiplexer import (
                WorkspaceMultiplexer,
            )

            WorkspaceMultiplexer.get().publish_session_status(params.chat_id, "awaiting_approval", "general")
        recording_info = getattr(agent, "_session_recording_info", None)
        if recording_info:
            yield {
                "type": "session_recording",
                "data": recording_info,
            }
