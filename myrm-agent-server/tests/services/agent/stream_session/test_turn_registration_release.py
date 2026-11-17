"""A turn gives back every registration it made, whichever way it leaves the turn body.

Finalize ends a turn that ran. The exits that skip it (a Stop while the turn waits behind its project's lock, a failure
in setup or in the pump) are covered by the safety net of the turn body. These tests drive the real turn body against the
real registries, so a registration left behind shows up as a live entry.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from types import SimpleNamespace
from typing import NamedTuple, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.agent.streaming.run_digest import RunDigestPhase
from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry, CancelReason
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.services.agent.goals import goal_branch_stash
from app.services.agent.goals.goal_registry import GoalRegistry
from app.services.agent.params import AgentRequest
from app.services.agent.steering import SteeringRegistry
from app.services.agent.stream_session import (
    chat_history_bootstrap,
    orchestrator_turn_body,
    pre_reply_compact_sse,
    stream_finalize,
    turn_end,
)
from app.services.agent.stream_session.stream_session_types import AgentStreamSession
from app.services.agent.streaming_support.stream_collector import ACTIVE_COLLECTORS, StreamContentCollector
from app.services.copilot.run_digest_store import RunDigestStore

CHAT_ID = "chat-release"
MESSAGE_ID = "msg-release"
MARKER_ID = "marker-release"

Pump = Callable[[AgentStreamSession, object], Awaitable[None]]
ExtraContext = Callable[..., Awaitable[dict[str, object]]]


class _Outcome(NamedTuple):
    clear_marker: AsyncMock
    lifecycle_event: MagicMock


@pytest.fixture(autouse=True)
def _isolated_registries() -> Iterator[None]:
    """A registration a failing test leaves behind must not leak into the next test."""

    def clean() -> None:
        with SteeringRegistry._lock:
            SteeringRegistry._tokens.pop(CHAT_ID, None)
        with GoalRegistry._lock:
            GoalRegistry._providers.pop(CHAT_ID, None)
        ACTIVE_COLLECTORS.pop(CHAT_ID, None)
        RunDigestStore.clear(CHAT_ID)
        CancellationRegistry.unregister(MESSAGE_ID)

    clean()
    yield
    clean()


def _request() -> AgentRequest:
    return cast(
        "AgentRequest",
        SimpleNamespace(
            message_id=MESSAGE_ID,
            chat_id=CHAT_ID,
            agent_id="agent-1",
            resume_value=None,
            engine_params=None,
            sibling_group_id=None,
            action_mode="agent",
            workspace_dir=None,
            goal=None,
        ),
    )


async def _context_with_goal(*_args: object, goal_provider: object, **_kwargs: object) -> dict[str, object]:
    return {"goal_provider": goal_provider}


def _stub_pipeline(monkeypatch: pytest.MonkeyPatch, pump: Pump, extra_context: ExtraContext = _context_with_goal) -> _Outcome:
    """Stub everything around the registrations (persistence, params, pump) and keep the registries real."""
    turn = SimpleNamespace(
        params=SimpleNamespace(turn_identity=None, message_id=MESSAGE_ID),
        extra_context={},
        routing_tier=None,
        archive_restore_results=None,
        routing_specialty=None,
        routing_reason=None,
        context_warnings=None,
    )

    async def persisted(*_args: object, **_kwargs: object) -> chat_history_bootstrap.BootstrappedMessageId:
        return chat_history_bootstrap.BootstrappedMessageId("msg-persisted")

    async def empty_history(*_args: object, **_kwargs: object) -> list[object]:
        return []

    async def nothing(*_args: object, **_kwargs: object) -> None:
        return None

    async def built_turn(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return turn

    async def written_marker(*_args: object, **_kwargs: object) -> str:
        return MARKER_ID

    clear_marker = AsyncMock()
    lifecycle_event = MagicMock()
    monkeypatch.setattr(chat_history_bootstrap, "persist_user_message", persisted)
    monkeypatch.setattr(chat_history_bootstrap, "load_chat_history", empty_history)
    monkeypatch.setattr(pre_reply_compact_sse, "run_pre_reply_compact_with_sse", nothing)
    monkeypatch.setattr(orchestrator_turn_body, "resolve_turn_history_mode", nothing)
    monkeypatch.setattr(orchestrator_turn_body, "apply_migration_bound_project", nothing)
    monkeypatch.setattr(orchestrator_turn_body, "build_turn_params", built_turn)
    monkeypatch.setattr(orchestrator_turn_body, "search_service_unavailable_detail", lambda *_args: None)
    monkeypatch.setattr(orchestrator_turn_body, "build_turn_extra_context", extra_context)
    monkeypatch.setattr(orchestrator_turn_body, "write_interrupted_turn_marker", written_marker)
    monkeypatch.setattr(orchestrator_turn_body, "pump_to_buffer", pump)
    monkeypatch.setattr(goal_branch_stash, "check_and_handle_branch_stash", nothing)
    monkeypatch.setattr("app.platform_utils.get_storage_provider", MagicMock())
    monkeypatch.setattr(stream_finalize, "_clear_interrupted_turn_marker", clear_marker)
    monkeypatch.setattr(turn_end, "publish_session_lifecycle_webhook_event", lifecycle_event)
    return _Outcome(clear_marker, lifecycle_event)


async def _run_turn_body() -> None:
    await orchestrator_turn_body.execute_agent_turn_after_reserve(
        request=_request(),
        http_request=SimpleNamespace(),
        text_content="hello",
        stream_started_at_monotonic=0.0,
        registry=SimpleNamespace(),
        buffer=SimpleNamespace(),
        record_terminal_failure=AsyncMock(),
    )


def _assert_no_registration_left() -> None:
    assert SteeringRegistry.get_token(CHAT_ID) is None
    assert GoalRegistry.get_provider(CHAT_ID) is None
    assert ACTIVE_COLLECTORS.get(CHAT_ID) is None


@pytest.mark.asyncio
async def test_a_turn_stopped_while_queued_gives_back_everything_and_closes_as_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pump swallows the cancel of a turn queued behind its project and returns without any finalize."""
    baseline = CancellationRegistry.get_active_count()

    async def pump_stopped_in_the_queue(session: AgentStreamSession, _buffer: object) -> None:
        session.cancel_token.cancel(CancelReason.USER_CANCELLED)

    outcome = _stub_pipeline(monkeypatch, pump_stopped_in_the_queue)

    await _run_turn_body()

    _assert_no_registration_left()
    assert CancellationRegistry.get_active_count() == baseline
    digest = RunDigestStore.get(CHAT_ID)
    assert digest is not None
    assert digest.phase is RunDigestPhase.CANCELLED
    outcome.clear_marker.assert_awaited_once_with(CHAT_ID, marker_id=MARKER_ID)
    outcome.lifecycle_event.assert_called_once()
    assert outcome.lifecycle_event.call_args.kwargs["phase"] is RunDigestPhase.CANCELLED
    assert outcome.lifecycle_event.call_args.kwargs["was_cancelled"] is True


@pytest.mark.asyncio
async def test_a_setup_failure_after_the_first_registration_gives_back_steering_and_goal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_context(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("context unavailable")

    async def pump_never_reached(_session: AgentStreamSession, _buffer: object) -> None:
        raise AssertionError("the pump must not start after a failed setup")

    _stub_pipeline(monkeypatch, pump_never_reached, extra_context=failing_context)

    with pytest.raises(RuntimeError, match="context unavailable"):
        await _run_turn_body()

    _assert_no_registration_left()
    assert RunDigestStore.get(CHAT_ID) is None


@pytest.mark.asyncio
async def test_a_pump_failure_closes_the_turn_as_failed_and_keeps_its_marker_for_the_crash_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = CancellationRegistry.get_active_count()

    async def pump_that_dies(_session: AgentStreamSession, _buffer: object) -> None:
        raise RuntimeError("pump died")

    outcome = _stub_pipeline(monkeypatch, pump_that_dies)

    with pytest.raises(RuntimeError, match="pump died"):
        await _run_turn_body()

    _assert_no_registration_left()
    assert CancellationRegistry.get_active_count() == baseline
    digest = RunDigestStore.get(CHAT_ID)
    assert digest is not None
    assert digest.phase is RunDigestPhase.ERROR
    outcome.clear_marker.assert_not_awaited()
    outcome.lifecycle_event.assert_called_once()
    assert outcome.lifecycle_event.call_args.kwargs["phase"] is RunDigestPhase.ERROR
    assert outcome.lifecycle_event.call_args.kwargs["had_fatal_error"] is True


@pytest.mark.asyncio
async def test_a_turn_whose_finalize_ended_is_left_to_finalize(monkeypatch: pytest.MonkeyPatch) -> None:
    """A turn parked at a HITL card keeps its collector and its open run: finalize decided that, not the net."""

    async def pump_after_finalize(session: AgentStreamSession, _buffer: object) -> None:
        session.torn_down = True

    outcome = _stub_pipeline(monkeypatch, pump_after_finalize)

    await _run_turn_body()

    assert ACTIVE_COLLECTORS.get(CHAT_ID) is not None
    digest = RunDigestStore.get(CHAT_ID)
    assert digest is not None
    assert digest.phase is RunDigestPhase.RUNNING
    outcome.clear_marker.assert_not_awaited()
    outcome.lifecycle_event.assert_not_called()


@pytest.mark.asyncio
async def test_a_late_teardown_leaves_the_registrations_of_the_turn_that_followed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A turn that ends late must give back only its own registrations: the chat's next turn may already hold the keys."""
    newer_steering = SteeringToken()
    newer: dict[str, object] = {}

    async def pump_overtaken(_session: AgentStreamSession, _buffer: object) -> None:
        SteeringRegistry.register(CHAT_ID, newer_steering)
        newer["goal"] = GoalRegistry.register(CHAT_ID)
        newer["collector"] = StreamContentCollector(sibling_group_id=None, chat_id=CHAT_ID)
        RunDigestStore.begin_run(CHAT_ID)

    outcome = _stub_pipeline(monkeypatch, pump_overtaken)

    await _run_turn_body()

    assert SteeringRegistry.get_token(CHAT_ID) is newer_steering
    assert GoalRegistry.get_provider(CHAT_ID) is newer["goal"]
    assert ACTIVE_COLLECTORS.get(CHAT_ID) is newer["collector"]
    digest = RunDigestStore.get(CHAT_ID)
    assert digest is not None
    assert digest.phase is RunDigestPhase.RUNNING
    outcome.lifecycle_event.assert_not_called()
