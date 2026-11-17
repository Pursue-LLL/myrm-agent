from __future__ import annotations

from unittest.mock import MagicMock, patch

from myrm_agent_harness.agent.streaming.run_digest import RunDigestPhase

from app.services.copilot.run_digest_store import RunDigestStore


def setup_method() -> None:
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
