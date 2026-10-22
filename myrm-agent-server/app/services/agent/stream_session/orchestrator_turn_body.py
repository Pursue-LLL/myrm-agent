"""Post-reserve agent turn execution for early buffered SSE (E1).

[INPUT]
- app.services.agent.stream_session.orchestrator helpers (POS: shared turn setup)
- app.services.agent.stream_session.orchestrator_turn_setup (POS: params, search gate, goal provider and runtime context of the turn)
- app.services.agent.stream_session.pre_reply_compact_sse (POS: idle compact SSE)
- app.services.agent.stream_session.turn_history_sync (POS: how the turn relates to the chat's agent thread)
- app.services.agent.stream_session.stream_pump::pump_to_buffer (POS: SSE pump)
- myrm_agent_harness.utils.runtime.cancellation::CancellationRegistry (POS: Stop handle of the turn, registered at turn entry)

[OUTPUT]
- execute_agent_turn_after_reserve: register cancel token → persist → pre-reply compact → history → agent session → pump (background)
- fail_buffered_turn: end a turn that failed before its stream started with an error SSE and release its cancel token
- write_interrupted_turn_marker: persist the write-ahead marker that makes a crashed turn recoverable

[POS]
E1 turn body: runs inside the background task started by orchestrator_turn_launch while clients already subscribe to the buffer during pre-reply compact and orchestrator setup.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from fastapi import Request
from myrm_agent_harness.runtime.context.session import HISTORY_MODE_CONTEXT_KEY
from myrm_agent_harness.utils.runtime.cancellation import (
    CancellationRegistry,
    CancellationToken,
)
from myrm_agent_harness.utils.runtime.steering import SteeringToken
from sqlalchemy import delete

from app.services.agent.params import (
    ArchiveRestoreRequestError,
)
from app.services.agent.steering import SteeringRegistry
from app.services.agent.stream_session import chat_history_bootstrap
from app.services.agent.stream_session.migration_bound_project import (
    apply_migration_bound_project,
)
from app.services.agent.stream_session.orchestrator_turn_setup import (
    build_turn_extra_context,
    build_turn_params,
    prepare_goal_provider,
    resolve_research_model,
    search_service_unavailable_detail,
)
from app.services.agent.stream_session.stream_pump import pump_to_buffer
from app.services.agent.stream_session.stream_session_types import AgentStreamSession
from app.services.agent.stream_session.turn_capability_terminal import (
    TurnCapabilityFailureReason,
)
from app.services.agent.stream_session.turn_history_sync import resolve_turn_history_mode
from app.services.agent.streaming_support.sse_helpers import error_sse
from app.services.agent.streaming_support.stream_collector import StreamContentCollector
from app.services.chat.compact_service import CompactResult

if TYPE_CHECKING:
    from myrm_agent_harness.agent.streaming.stream_buffer import GlobalStreamRegistry, ResilientStreamBuffer

    from app.ai_agents import GeneralAgentParams
    from app.services.agent.params import AgentRequest

logger = logging.getLogger(__name__)


async def fail_buffered_turn(
    buffer: ResilientStreamBuffer,
    message_id: str,
    detail: str,
) -> None:
    """End a turn that failed before its stream started: emit the error SSE and close the buffer."""
    # A turn that fails during setup never reaches stream finalize, which is
    # where a normally finished turn unregisters its cancel token.
    CancellationRegistry.unregister(message_id)
    await buffer.append(error_sse(detail, message_id))
    await buffer.end_stream()


async def execute_agent_turn_after_reserve(
    *,
    request: AgentRequest,
    http_request: Request,
    text_content: str,
    stream_started_at_monotonic: float,
    registry: GlobalStreamRegistry,
    buffer: ResilientStreamBuffer,
    record_terminal_failure: Callable[[TurnCapabilityFailureReason], Awaitable[None]],
) -> None:
    """Run persist → pre-reply compact → session build → pump after the HTTP response is already accepted."""
    # Registered before the first await so a Stop that lands during setup finds this turn.
    cancel_token = CancellationToken(request_id=request.message_id)
    CancellationRegistry.register(cancel_token)

    # Commit the user row before any optional profile/model-window/compact work.
    # The multiplexed HTTP response is already accepted at this point; API
    # observers must see the turn even when stale-context setup is slow.
    persisted_message_id = await chat_history_bootstrap.persist_user_message(
        request,
        text_content=text_content,
    )
    pending_draft = persisted_message_id.pending_draft if persisted_message_id is not None else None

    pre_reply_compact_result: CompactResult | None = None
    pre_reply_compact_sse_sent = False
    if request.resume_value is None and request.chat_id and request.message_id:
        from app.services.agent.stream_session.pre_reply_compact_sse import (
            run_pre_reply_compact_with_sse,
        )

        pre_reply_compact_result = await run_pre_reply_compact_with_sse(
            buffer,
            chat_id=request.chat_id,
            message_id=request.message_id,
            agent_id=request.agent_id,
            request_engine_params=request.engine_params,
        )
        pre_reply_compact_sse_sent = bool(
            pre_reply_compact_result
            and (
                (pre_reply_compact_result.compacted and pre_reply_compact_result.tokens_saved > 0)
                or pre_reply_compact_result.attempted
            )
        )

    chat_history = await chat_history_bootstrap.load_chat_history(
        request,
        exclude_message_id=persisted_message_id,
    )
    history_mode = await resolve_turn_history_mode(request, exclude_message_id=persisted_message_id)

    await apply_migration_bound_project(request)

    try:
        turn = await build_turn_params(request, chat_history, http_request)
    except ArchiveRestoreRequestError as exc:
        await record_terminal_failure("archive_restore_invalid")
        await fail_buffered_turn(buffer, request.message_id, str(exc))
        return
    params = turn.params

    research_model_cfg = await resolve_research_model(request)

    unavailable_detail = search_service_unavailable_detail(request, params)
    if unavailable_detail is not None:
        await record_terminal_failure("server_error")
        await fail_buffered_turn(buffer, request.message_id, unavailable_detail)
        return

    steering_token = SteeringToken() if request.chat_id else None
    if steering_token and request.chat_id:
        SteeringRegistry.register(request.chat_id, steering_token)

    goal_provider = await prepare_goal_provider(request, text_content)
    extra_context = await build_turn_extra_context(
        request,
        params,
        base=turn.extra_context,
        goal_provider=goal_provider,
    )
    if history_mode is not None:
        extra_context[HISTORY_MODE_CONTEXT_KEY] = history_mode

    is_long_running_task = request.action_mode in ("deep_research", "agentic_search")
    collector = StreamContentCollector(sibling_group_id=request.sibling_group_id, chat_id=request.chat_id)
    if request.chat_id:
        from app.services.copilot.run_digest_store import RunDigestStore

        RunDigestStore.begin_run(request.chat_id)

    session = AgentStreamSession(
        request=request,
        http_request=http_request,
        params=params,
        cancel_token=cancel_token,
        steering_token=steering_token,
        routing_tier=turn.routing_tier,
        archive_restore_results=turn.archive_restore_results,
        research_model_cfg=research_model_cfg,
        registry=registry,
        collector=collector,
        is_long_running_task=is_long_running_task,
        goal_provider=goal_provider,
        extra_context=extra_context,
        routing_specialty=turn.routing_specialty,
        routing_reason=turn.routing_reason,
        context_warnings=turn.context_warnings,
        stream_started_at_monotonic=stream_started_at_monotonic,
        pre_reply_compact_result=pre_reply_compact_result,
        pre_reply_compact_sse_sent=pre_reply_compact_sse_sent,
        pending_session_draft=pending_draft,
    )

    if request.chat_id and request.resume_value is None and not is_long_running_task:
        if pending_draft is None or getattr(pending_draft, "committed", False):
            try:
                await write_interrupted_turn_marker(request, params, user_message_id=persisted_message_id)
            except Exception as marker_exc:
                logger.debug("Turn marker write skipped: %s", marker_exc)

    await pump_to_buffer(session, buffer)


async def write_interrupted_turn_marker(
    request: AgentRequest,
    params: GeneralAgentParams,
    *,
    user_message_id: str | None = None,
) -> None:
    """Persist a write-ahead marker so a crash leaves a recoverable trace.

    ``user_message_id`` is the id the user row was stored under, which can differ from the request's
    id; replay excludes that row from history because the turn's query is replayed separately.
    """
    from app.database.models.chat import InterruptedTurnMarker
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        await db.execute(delete(InterruptedTurnMarker).where(InterruptedTurnMarker.chat_id == request.chat_id))
        marker = InterruptedTurnMarker(
            id=str(uuid.uuid4()),
            chat_id=request.chat_id,
            user_message_id=user_message_id or request.message_id or "",
            action_mode=request.action_mode or "fast",
            agent_id=getattr(request, "agent_id", None),
            serialized_params=params.model_dump(mode="json", exclude={"chat_history"}),
        )
        db.add(marker)
        await db.commit()
