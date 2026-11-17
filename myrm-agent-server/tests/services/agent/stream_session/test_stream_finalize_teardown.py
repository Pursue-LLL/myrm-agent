"""What the end of a turn leaves behind: the stored message, the crash marker, the registrations and the run record.

Real scenario: a turn ends, whether the answer finished or the user pressed Stop. The answer is stored with how long
the first token took, the write-ahead marker that would resume a crashed turn is cleared only once the answer is
stored, the Stop handle, steering registration and goal provider the turn held are given back (the provider by its
own handle, so a turn the server started meanwhile keeps its own), and a stopped turn is recorded as stopped instead
of finished.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.streaming.run_digest import RunDigestPhase

from app.services.agent.goals.goal_registry import GoalRegistry
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
        self.goal_registry = MagicMock()
        self.end_run = MagicMock()
        self.capability_failed = AsyncMock()


@contextmanager
def _collaborators(teardown: _Teardown, *, goal_registry: object | None = None) -> Iterator[None]:
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
        stack.enter_context(
            patch(
                "app.services.agent.goals.goal_registry.GoalRegistry",
                teardown.goal_registry if goal_registry is None else goal_registry,
            )
        )
        stack.enter_context(patch("app.services.chat.chat_service.ChatService.persist_assistant_message_safe", teardown.persist))
        stack.enter_context(patch("app.services.copilot.run_digest_store.RunDigestStore.end_run", teardown.end_run))
        stack.enter_context(
            patch("myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics", return_value=None)
        )
        stack.enter_context(patch("myrm_agent_harness.api.hooks.get_memory_runtime_budget", return_value=None))
        stack.enter_context(patch("myrm_agent_harness.api.hooks.get_memory_runtime_injection", return_value=None))
        yield


async def _end_turn(session: MagicMock, *, goal_registry: object | None = None) -> _Teardown:
    teardown = _Teardown()
    with _collaborators(teardown, goal_registry=goal_registry):
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
async def test_the_turn_gives_back_its_stop_handle_and_the_steering_token_it_registered() -> None:
    session = _make_session()

    teardown = await _end_turn(session)

    teardown.cancellation.unregister.assert_called_once_with(MESSAGE_ID)
    teardown.steering.unregister.assert_called_once_with(CHAT_ID, session.steering_token)


@pytest.mark.asyncio
async def test_the_turn_gives_back_the_goal_provider_it_registered() -> None:
    session = _make_session()

    teardown = await _end_turn(session)

    teardown.goal_registry.unregister.assert_called_once_with(CHAT_ID, session.goal_provider)


@pytest.mark.asyncio
async def test_a_turn_without_a_goal_provider_gives_back_no_goal_registration() -> None:
    session = _make_session()
    session.goal_provider = None

    teardown = await _end_turn(session)

    teardown.goal_registry.unregister.assert_not_called()


@pytest.mark.asyncio
async def test_a_turn_the_server_started_meanwhile_keeps_its_goal_registration_through_this_teardown() -> None:
    """The gateway gives the session back before the teardown ends, so the server can start the chat's next turn in
    between; the teardown then finds the registration of that turn and leaves it."""
    with patch("app.platform_utils.get_storage_provider", return_value=MagicMock()):
        session = _make_session()
        session.goal_provider = GoalRegistry.register(CHAT_ID)
        started_meanwhile = GoalRegistry.register(CHAT_ID)

        await _end_turn(session, goal_registry=GoalRegistry)

    assert GoalRegistry.get_provider(CHAT_ID) is started_meanwhile


@pytest.mark.asyncio
async def test_a_turn_the_user_stopped_is_recorded_as_stopped() -> None:
    session = _make_session(cancelled=True)

    teardown = await _end_turn(session)

    teardown.end_run.assert_called_once_with(CHAT_ID, phase=RunDigestPhase.CANCELLED, progress_steps=[], run=session.digest_run)
    teardown.capability_failed.assert_awaited_once_with(session, "abort")


@pytest.mark.asyncio
async def test_a_turn_is_torn_down_once_finalize_has_run_to_its_end() -> None:
    session = _make_session()
    session.torn_down = False

    await _end_turn(session)

    assert session.torn_down is True


@pytest.mark.asyncio
async def test_a_turn_parked_for_an_answer_is_torn_down_but_keeps_its_collector_and_its_run() -> None:
    session = _make_session()
    session.torn_down = False
    session.collector.has_pending_hitl_replay.return_value = True

    teardown = await _end_turn(session)

    assert session.torn_down is True
    teardown.end_run.assert_not_called()
    session.collector.cleanup.assert_not_called()
