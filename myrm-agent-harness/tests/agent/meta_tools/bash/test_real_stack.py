"""The real-stack helper gives up on a background job that never ends instead of reporting a result for it.

``RealBashStack.run_background`` waits for a job to end and returns what it printed. A job that has not ended is no
result: the helper raises ``TimeoutError`` naming what the job had printed, and it kills the job it started, so that no
child process and no slot of the session's background-job limit outlives the call.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator

import pytest

from myrm_agent_harness.agent.meta_tools.bash._background.registry import get_background_registry
from myrm_agent_harness.toolkits.code_execution.executors.local import _background_pty_spawn
from tests.agent.meta_tools.bash import real_stack as helper
from tests.agent.meta_tools.bash.real_stack import SESSION_ID, RealBashStack
from tests.support.marked_processes import kill_marked, process_alive, wait_until

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell semantics")

# The digits are the worker's pid, so parallel test workers never stop each other's sleepers; ``sleep`` accepts digits
# only.
_SLEEPER = f"sleep 4761.{os.getpid():09d}"
# The shell computes the word it prints, so the command text alone never contains it.
_PRINT_THEN_NEVER_END = f"echo ready-$((6 * 7)); {_SLEEPER}"


@pytest.fixture(autouse=True)
def _fake_pids_have_no_process_group() -> None:
    """The jobs here are real processes, so the real process-group lookup applies."""


@pytest.fixture(autouse=True)
def _remove_sleepers() -> Iterator[None]:
    yield
    kill_marked(_SLEEPER)


@pytest.fixture(autouse=True)
def _wait_one_second(monkeypatch: pytest.MonkeyPatch) -> None:
    """A job that never ends costs the helper its whole wait, so the wait is cut from ten seconds to one."""
    monkeypatch.setattr(helper, "_BACKGROUND_WAIT_SECONDS", 1)


async def test_a_job_that_does_not_end_makes_the_helper_raise_with_what_it_printed(
    shared_real_stack: RealBashStack,
) -> None:
    with pytest.raises(TimeoutError) as raised:
        await shared_real_stack.run_background(_PRINT_THEN_NEVER_END)

    assert _SLEEPER in str(raised.value)
    assert "ready-42" in str(raised.value)


@pytest.mark.parametrize("on_pty", [True, False], ids=["pty", "pipes"])
async def test_the_helper_kills_the_job_it_gave_up_on(
    shared_real_stack: RealBashStack, monkeypatch: pytest.MonkeyPatch, on_pty: bool
) -> None:
    if not on_pty:
        monkeypatch.setattr(_background_pty_spawn, "pty_spawn_eligible", lambda *, sandbox_enabled: False)
    registry = get_background_registry()
    known = {info.pid for info in registry.list_processes(SESSION_ID)}
    running_before = registry.count_running(SESSION_ID)

    with pytest.raises(TimeoutError):
        await shared_real_stack.run_background(_SLEEPER)

    started = [info for info in registry.list_processes(SESSION_ID) if info.pid not in known]
    assert [info.status for info in started] == ["killed"]
    assert registry.count_running(SESSION_ID) == running_before
    await wait_until(lambda: not process_alive(_SLEEPER))
