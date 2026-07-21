"""Agent streaming services.

Bridges Agent/Orchestrator → AgentGateway → SSE output.

[INPUT]
- ai_agents::AgentFactory, GeneralAgentParams
- services.agent.gateway::get_agent_gateway
- app.services.approvals.registry::ApprovalRegistry (POS: 统一的拦截审批注册与唤醒中枢)
- myrm_agent_harness.agent.meta_tools.clarification::AskQuestionInput (POS: 深研究澄清表单结构输入)

[OUTPUT]
- ai_agent_service_stream: General Agent SSE stream (budget_blocked semantic code; progress.started without UI copy)
- ai_deep_research_service_stream: Deep Research SSE stream
- PhaseWaiter: Generic in-process suspend/resume for Deep Research phases (clarification, plan confirmation)
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
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.ai_agents import AgentFactory, GeneralAgentParams
from app.core.utils.chat_utils import convert_chat_history
from app.services.agent.gateway import get_agent_gateway

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import BaseMessage
    from langchain_core.tools import BaseTool
    from myrm_agent_harness.agent.deep_research.helpers import DeepResearchResult
    from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
    from myrm_agent_harness.utils.runtime.steering import SteeringToken

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PhaseWaiter — generic in-process suspend/resume for Deep Research phases
# ---------------------------------------------------------------------------

PhaseAnswer = str | list[str] | dict[str, str | list[str]] | None

PHASE_TIMEOUT_SECONDS = 300

_phase_waiters: dict[str, "PhaseWaiter"] = {}

_TAKEOVER_REASON_MAX_CHARS = 280
_TAKEOVER_PAGE_URL_MAX_CHARS = 1024
_TAKEOVER_MESSAGE_ID_MAX_CHARS = 256
TakeoverLiveAssistCache = tuple[str, str]


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


def _clamp_takeover_context(value: object, max_chars: int) -> str:
    if not isinstance(value, str):
        return ""
    trimmed = value.strip()
    if not trimmed:
        return ""
    return trimmed[:max_chars]


def _event_with_mutable_data(event: object) -> tuple[dict[str, object], dict[str, object]] | None:
    if isinstance(event, dict):
        data = event.get("data")
        if not isinstance(data, dict):
            data = {}
            event["data"] = data
        return event, data

    if hasattr(event, "to_dict"):
        event_dict = event.to_dict()
    elif hasattr(event, "model_dump"):
        event_dict = event.model_dump()
    else:
        return None

    if not isinstance(event_dict, dict):
        return None
    data = event_dict.get("data")
    if not isinstance(data, dict):
        data = {}
        event_dict["data"] = data
    return event_dict, data


def _compose_takeover_live_assist_url(
    base_url_or_path: str,
    *,
    message_id: str,
    reason: str,
    page_url: str,
) -> str:
    parts = urlsplit(base_url_or_path)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if message_id:
        query["mid"] = message_id
    if reason:
        query["reason"] = reason
    if page_url:
        query["page"] = page_url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


async def _create_takeover_live_assist_url(
    *,
    chat_id: str | None,
    message_id: str,
    reason: object,
    page_url: object,
    is_managed: bool,
) -> str | None:
    normalized_chat_id = _clamp_takeover_context(chat_id, 128)
    if not normalized_chat_id or is_managed:
        return None

    from app.remote_access.pairing import BROWSER_TAKEOVER_PURPOSE, create_pairing_token
    from app.remote_access.pairing_links import (
        mobile_path_for_pairing_token,
        mobile_url_for_path,
    )

    token = create_pairing_token(
        chat_id=normalized_chat_id,
        purpose=BROWSER_TAKEOVER_PURPOSE,
    )
    mobile_path = mobile_path_for_pairing_token(
        token=token,
        purpose=BROWSER_TAKEOVER_PURPOSE,
        chat_id=normalized_chat_id,
    )
    absolute_url = await mobile_url_for_path(mobile_path)
    entry_url = absolute_url or mobile_path
    return _compose_takeover_live_assist_url(
        entry_url,
        message_id=_clamp_takeover_context(message_id, _TAKEOVER_MESSAGE_ID_MAX_CHARS),
        reason=_clamp_takeover_context(reason, _TAKEOVER_REASON_MAX_CHARS),
        page_url=_clamp_takeover_context(page_url, _TAKEOVER_PAGE_URL_MAX_CHARS),
    )


def _read_live_assist_url(payload: dict[str, object]) -> str:
    value = payload.get("live_assist_url")
    return value.strip() if isinstance(value, str) else ""


def _is_managed_takeover(payload: dict[str, object], fallback: dict[str, object]) -> bool:
    payload_flag = payload.get("is_managed")
    if isinstance(payload_flag, bool):
        return payload_flag
    fallback_flag = fallback.get("is_managed")
    return isinstance(fallback_flag, bool) and fallback_flag


def _takeover_cache_key(*, reason: object, page_url: object, is_managed: bool) -> str:
    return "|".join(
        [
            "managed" if is_managed else "extension",
            _clamp_takeover_context(reason, _TAKEOVER_REASON_MAX_CHARS),
            _clamp_takeover_context(page_url, _TAKEOVER_PAGE_URL_MAX_CHARS),
        ]
    )


async def _inject_takeover_live_assist_url(
    event: object,
    *,
    chat_id: str | None,
    message_id: str,
    cached: TakeoverLiveAssistCache | None,
) -> tuple[object, TakeoverLiveAssistCache | None]:
    event_type = getattr(event, "type", None) if not isinstance(event, dict) else event.get("type")
    if event_type not in {"browser_takeover_requested", "approval_required"}:
        return event, cached

    event_pair = _event_with_mutable_data(event)
    if event_pair is None:
        return event, cached
    event_dict, event_data = event_pair

    if event_type == "browser_takeover_requested":
        existing = _read_live_assist_url(event_data)
        is_managed = _is_managed_takeover(event_data, event_data)
        if is_managed:
            return event_dict, cached
        cache_key = _takeover_cache_key(
            reason=event_data.get("reason"),
            page_url=event_data.get("url"),
            is_managed=is_managed,
        )
        if existing:
            return event_dict, (cache_key, existing)
        if cached and cached[0] == cache_key:
            live_assist_url = cached[1]
        else:
            live_assist_url = await _create_takeover_live_assist_url(
                chat_id=chat_id,
                message_id=message_id,
                reason=event_data.get("reason"),
                page_url=event_data.get("url"),
                is_managed=is_managed,
            )
        if live_assist_url:
            event_data["live_assist_url"] = live_assist_url
            return event_dict, (cache_key, live_assist_url)
        return event_dict, cached

    action_type = event_data.get("action_type")
    if action_type != "browser_takeover":
        return event_dict, cached

    takeover_payload = event_data.get("payload")
    takeover_data = takeover_payload if isinstance(takeover_payload, dict) else event_data
    is_managed = _is_managed_takeover(takeover_data, event_data)
    if is_managed:
        return event_dict, cached
    cache_key = _takeover_cache_key(
        reason=takeover_data.get("reason", event_data.get("reason")),
        page_url=takeover_data.get("url", event_data.get("url")),
        is_managed=is_managed,
    )
    existing = _read_live_assist_url(takeover_data)
    if existing:
        if "live_assist_url" not in event_data:
            event_data["live_assist_url"] = existing
        return event_dict, (cache_key, existing)

    if cached and cached[0] == cache_key:
        live_assist_url = cached[1]
    else:
        live_assist_url = await _create_takeover_live_assist_url(
            chat_id=chat_id,
            message_id=message_id,
            reason=takeover_data.get("reason", event_data.get("reason")),
            page_url=takeover_data.get("url", event_data.get("url")),
            is_managed=is_managed,
        )
    if not live_assist_url:
        return event_dict, cached

    takeover_data["live_assist_url"] = live_assist_url
    if isinstance(takeover_payload, dict):
        event_data["payload"] = takeover_data
    event_data["live_assist_url"] = live_assist_url
    return event_dict, (cache_key, live_assist_url)




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
        takeover_live_assist_cache: TakeoverLiveAssistCache | None = None
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
                event, takeover_cache = await _inject_takeover_live_assist_url(
                    event,
                    chat_id=params.chat_id,
                    message_id=params.message_id,
                    cached=takeover_live_assist_cache,
                )
                takeover_live_assist_cache = takeover_cache
            except Exception as ex:
                logger.warning("Failed to inject takeover live assist URL: %s", ex)

            # Intercept APPROVAL_REQUIRED events to persist to DB
            event_type = getattr(event, "type", None) if not isinstance(event, dict) else event.get("type")
            if event_type == "approval_required":
                from app.services.approvals.registry import ApprovalRegistry

                approval_data = getattr(event, "data", {}) if not isinstance(event, dict) else event.get("data", {})
                if isinstance(approval_data, dict):
                    thread_id = params.chat_id or params.message_id

                    action_type = approval_data.get("action_type", "unknown")

                    try:
                        from app.services.agent.approval_payload import extract_approval_registry_payload

                        approval_payload = extract_approval_registry_payload(approval_data)
                        if params.message_id:
                            approval_payload = {**approval_payload, "messageId": params.message_id}
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
        recording_info = getattr(agent, "_session_recording_info", None)
        if recording_info:
            yield {
                "type": "session_recording",
                "data": recording_info,
            }


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
        _phase_waiters.pop(message_id, None)
        _phase_waiters.pop(f"plan:{message_id}", None)

    if producer_error is not None:
        raise producer_error
