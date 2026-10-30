"""What the end of a turn leaves behind: the stored message, the crash marker, the registrations and the run record.

Real scenario: a turn ends, whether the answer finished or the user pressed Stop. The answer is stored with how long
the first token took, the write-ahead marker that would resume a crashed turn is cleared only once the answer is
stored, the Stop handle and steering registration the turn held are given back, and a stopped turn is recorded as
stopped instead of finished.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.streaming.run_digest import RunDigestPhase

from app.services.agent.stream_session.stream_finalize import finalize_agent_stream_session
from app.services.agent.stream_session.stream_loop import ApprovalTimeoutHolder, ClarificationTimeoutHolder

_FINALIZE = "app.services.agent.stream_session.stream_finalize"
CHAT_ID = "chat-teardown"
MESSAGE_ID = "msg-teardown"


def _make_session(*, cancelled: bool = False) -> MagicMock:
    session = MagicMock()
    session.pending_session_draft = None
    session.request.chat_id = CHAT_ID
    session.request.message_id = MESSAGE_ID
    session.request.timezone = "UTC"
    session.request.resume_value = None
    session.cancel_token.is_cancelled = cancelled
    session.params.message_id = MESSAGE_ID
    session.collector.has_persistable_turn = True
    session.collector.has_content = True
    session.collector.content = "The answer"
    session.collector.extra_data = {}
    session.collector.sibling_group_id = None
    session.collector.has_pending_hitl_replay.return_value = False
    session.collector._progress_steps = []
    session.extra_context = {}
    session.stream_ttft_ms = None
    session.had_fatal_error = False
    session.migration_live_readiness_status = None
    return session


class _Teardown:
    """The collaborators of one finalize call, so a test can read what the end of the turn did to each."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.persist = AsyncMock(side_effect=lambda *_a, **_k: self.calls.append("persist"))
        self.clear_marker = AsyncMock(side_effect=lambda *_a, **_k: self.calls.append("marker"))
        self.cancellation = MagicMock()
        self.steering = MagicMock()
        self.end_run = MagicMock()
        self.capability_failed = AsyncMock()


@contextmanager
def _collaborators(teardown: _Teardown) -> Iterator[None]:
    with ExitStack() as stack:
        for name in ("clear_context_task_metrics", "enqueue_context_compaction_telemetry", "merge_memory_citation_fallback"):
            stack.enter_context(patch(f"{_FINALIZE}.{name}"))
        stack.enter_context(patch(f"{_FINALIZE}.user_credentials_ctx"))
        stack.enter_context(patch(f"{_FINALIZE}.record_migration_first_turn_outcome", new_callable=AsyncMock))
        stack.enter_context(patch(f"{_FINALIZE}.CancellationRegistry", teardown.cancellation))
        stack.enter_context(patch(f"{_FINALIZE}.SteeringRegistry", teardown.steering))
        stack.enter_context(patch(f"{_FINALIZE}._clear_interrupted_turn_marker", teardown.clear_marker))
        stack.enter_context(patch(f"{_FINALIZE}.has_turn_capability_terminal_context", return_value=True))
        stack.enter_context(patch(f"{_FINALIZE}.record_turn_capability_failed_once", teardown.capability_failed))
        stack.enter_context(patch("app.services.agent.goals.goal_registry.GoalRegistry"))
        stack.enter_context(patch("app.services.chat.chat_service.ChatService.persist_assistant_message_safe", teardown.persist))
        stack.enter_context(patch("app.services.copilot.run_digest_store.RunDigestStore.end_run", teardown.end_run))
        stack.enter_context(
            patch("myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics", return_value=None)
        )
        stack.enter_context(patch("myrm_agent_harness.api.hooks.get_memory_runtime_budget", return_value=None))
        stack.enter_context(patch("myrm_agent_harness.api.hooks.get_memory_runtime_injection", return_value=None))
        yield


async def _end_turn(session: MagicMock) -> _Teardown:
    teardown = _Teardown()
    with _collaborators(teardown):
        await finalize_agent_stream_session(session, MagicMock(), ApprovalTimeoutHolder(), ClarificationTimeoutHolder())
    return teardown


@pytest.mark.asyncio
async def test_a_finished_answer_is_stored_with_its_first_token_latency_and_sibling_group() -> None:
    session = _make_session()
    session.stream_ttft_ms = 420
    session.collector.sibling_group_id = "sibling-1"

    teardown = await _end_turn(session)

    stored = teardown.persist.await_args
    assert stored is not None
    assert stored.kwargs["extra_data"]["streamTtftMs"] == 420
    assert stored.kwargs["sibling_group_id"] == "sibling-1"


@pytest.mark.asyncio
async def test_the_crash_marker_is_cleared_only_after_the_answer_is_stored() -> None:
    teardown = await _end_turn(_make_session())

    assert teardown.calls == ["persist", "marker"]
    teardown.clear_marker.assert_awaited_once_with(CHAT_ID)


@pytest.mark.asyncio
async def test_the_turn_gives_back_its_stop_handle_and_steering_registration() -> None:
    teardown = await _end_turn(_make_session())

    teardown.cancellation.unregister.assert_called_once_with(MESSAGE_ID)
    teardown.steering.unregister.assert_called_once_with(CHAT_ID)


@pytest.mark.asyncio
async def test_a_turn_the_user_stopped_is_recorded_as_stopped() -> None:
    session = _make_session(cancelled=True)

    teardown = await _end_turn(session)

    teardown.end_run.assert_called_once_with(CHAT_ID, phase=RunDigestPhase.CANCELLED, progress_steps=[])
    teardown.capability_failed.assert_awaited_once_with(session, "abort")
