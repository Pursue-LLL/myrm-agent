from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.agent.streaming.run_digest import RunDigestPhase

from app.services.copilot.run_digest_store import RunDigestStore


@pytest.fixture(autouse=True)
def _empty_store() -> Iterator[None]:
    """The store is process-wide: a digest one test leaves behind must not be read by the next."""
    RunDigestStore._digests.clear()
    RunDigestStore._sessions.clear()
    yield
    RunDigestStore._digests.clear()
    RunDigestStore._sessions.clear()


def test_begin_and_update_progress() -> None:
    RunDigestStore.begin_run("chat-a")
    RunDigestStore.update_from_progress(
        "chat-a",
        [{"tool_name": "read_file", "step_key": "r1", "status": "done"}],
    )
    digest = RunDigestStore.get("chat-a")
    assert digest is not None
    assert digest.phase == RunDigestPhase.RUNNING
    assert digest.step_count == 1
    assert digest.current_tool == "read_file"


def test_set_pending_approval_count_switches_phase() -> None:
    RunDigestStore.begin_run("chat-b")
    RunDigestStore.set_pending_approval_count("chat-b", 2)
    digest = RunDigestStore.get("chat-b")
    assert digest is not None
    assert digest.phase == RunDigestPhase.WAITING_APPROVAL
    assert digest.pending_approval_count == 2


def test_end_run_publishes_sse() -> None:
    mock_bus = MagicMock()
    with patch("app.services.copilot.run_digest_store.get_event_bus", return_value=mock_bus):
        RunDigestStore.begin_run("chat-c")
        RunDigestStore.end_run(
            "chat-c",
            phase=RunDigestPhase.COMPLETED,
            progress_steps=[{"tool_name": "done_tool", "step_key": "d1"}],
        )
    digest = RunDigestStore.get("chat-c")
    assert digest is not None
    assert digest.phase == RunDigestPhase.COMPLETED
    assert mock_bus.publish.called


def test_end_run_by_handle_ends_the_run_once() -> None:
    run = RunDigestStore.begin_run("chat-d")
    assert run is not None

    assert RunDigestStore.end_run("chat-d", phase=RunDigestPhase.CANCELLED, run=run) is True
    assert RunDigestStore.end_run("chat-d", phase=RunDigestPhase.ERROR, run=run) is False

    digest = RunDigestStore.get("chat-d")
    assert digest is not None
    assert digest.phase == RunDigestPhase.CANCELLED


def test_end_run_by_handle_leaves_the_run_of_a_turn_that_started_after() -> None:
    """A turn that ends late must not close the run the chat's next turn is showing."""
    ended = RunDigestStore.begin_run("chat-e")
    newer = RunDigestStore.begin_run("chat-e")

    assert RunDigestStore.end_run("chat-e", phase=RunDigestPhase.CANCELLED, run=ended) is False

    digest = RunDigestStore.get("chat-e")
    assert digest is not None
    assert digest.phase == RunDigestPhase.RUNNING
    assert RunDigestStore.end_run("chat-e", phase=RunDigestPhase.COMPLETED, run=newer) is True


def test_end_run_without_a_handle_ends_whichever_run_is_live() -> None:
    RunDigestStore.begin_run("chat-f")

    assert RunDigestStore.end_run("chat-f", phase=RunDigestPhase.COMPLETED) is True

    digest = RunDigestStore.get("chat-f")
    assert digest is not None
    assert digest.phase == RunDigestPhase.COMPLETED


def test_an_approval_no_run_owns_leaves_the_chat_idle_once_resolved() -> None:
    """An outbound draft is approved outside any turn: nothing would end a run the approval opened."""
    RunDigestStore.set_pending_approval_count("chat-g", 1)
    waiting = RunDigestStore.get("chat-g")
    assert waiting is not None
    assert waiting.phase == RunDigestPhase.WAITING_APPROVAL

    RunDigestStore.set_pending_approval_count("chat-g", 0)

    digest = RunDigestStore.get("chat-g")
    assert digest is not None
    assert digest.phase == RunDigestPhase.IDLE
    assert RunDigestStore.terminal_failures() == []


def test_an_approval_raised_after_a_run_ended_resolves_to_idle_not_running() -> None:
    RunDigestStore.begin_run("chat-h")
    RunDigestStore.end_run("chat-h", phase=RunDigestPhase.COMPLETED)

    RunDigestStore.set_pending_approval_count("chat-h", 1)
    RunDigestStore.set_pending_approval_count("chat-h", 0)

    digest = RunDigestStore.get("chat-h")
    assert digest is not None
    assert digest.phase == RunDigestPhase.IDLE


def test_a_count_of_zero_without_a_live_run_changes_nothing() -> None:
    RunDigestStore.begin_run("chat-i")
    RunDigestStore.end_run("chat-i", phase=RunDigestPhase.COMPLETED)

    RunDigestStore.set_pending_approval_count("chat-i", 0)

    digest = RunDigestStore.get("chat-i")
    assert digest is not None
    assert digest.phase == RunDigestPhase.COMPLETED


def test_resolving_the_approvals_of_a_live_run_returns_it_to_running() -> None:
    RunDigestStore.begin_run("chat-j")
    RunDigestStore.set_pending_approval_count("chat-j", 1)

    RunDigestStore.set_pending_approval_count("chat-j", 0)

    digest = RunDigestStore.get("chat-j")
    assert digest is not None
    assert digest.phase == RunDigestPhase.RUNNING


def test_a_turn_that_reports_progress_owns_the_run_an_approval_opened() -> None:
    """A turn resumed by the approval timer never calls begin_run: its progress makes the run its own and its end closes it."""
    RunDigestStore.set_pending_approval_count("chat-k", 1)
    RunDigestStore.update_from_progress("chat-k", [{"tool_name": "bash", "step_key": "k1", "status": "running"}])

    RunDigestStore.set_pending_approval_count("chat-k", 0)

    running = RunDigestStore.get("chat-k")
    assert running is not None
    assert running.phase == RunDigestPhase.RUNNING
    assert RunDigestStore.end_run("chat-k", phase=RunDigestPhase.COMPLETED) is True
    completed = RunDigestStore.get("chat-k")
    assert completed is not None
    assert completed.phase == RunDigestPhase.COMPLETED
