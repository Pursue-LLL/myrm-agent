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
