"""What a kill tells the model: what the stop found, and nothing the platform could not see."""

from __future__ import annotations

from myrm_agent_harness.agent.meta_tools.bash._tool.process_handlers import kill_report


def _report(
    *,
    force: bool = False,
    ok: bool = True,
    was_running: bool = True,
    left_before: int = 0,
    leftover: int = 0,
    group_visible: bool = True,
) -> str:
    return kill_report(
        7,
        force=force,
        ok=ok,
        was_running=was_running,
        left_before=left_before,
        leftover=leftover,
        group_visible=group_visible,
    )


def test_the_kill_report_never_claims_a_stop_that_did_not_happen() -> None:
    survived = _report(leftover=2)
    assert "2 process(es)" in survived
    assert "still running" in survived
    assert "SIGTERM then SIGKILL" in survived

    survived_force = _report(force=True, leftover=1)
    assert "still running" in survived_force
    assert "Sent SIGKILL to pid=7" in survived_force

    # Nothing outlives SIGKILL by being asked again, so the report offers no retry.
    assert "force=true" not in survived + survived_force

    stopped = _report()
    assert stopped.startswith("Stopped pid=7")
    assert "no process it started was found still running" in stopped
    assert "detached themselves are not tracked" in stopped
    finished = _report(was_running=False)
    assert "already finished" in finished
    assert "was found still running" in finished
    assert "detached themselves are not tracked" in finished
    assert "stopped the 2 process(es)" in _report(was_running=False, left_before=2)
    assert _report(ok=False).startswith("Failed")


def test_the_kill_report_claims_nothing_where_the_platform_cannot_list_a_group() -> None:
    assert _report(group_visible=False) == "Sent SIGTERM to pid=7"
    assert _report(force=True, group_visible=False) == "Sent SIGKILL to pid=7"
    assert _report(was_running=False, group_visible=False) == "pid=7 had already finished."
