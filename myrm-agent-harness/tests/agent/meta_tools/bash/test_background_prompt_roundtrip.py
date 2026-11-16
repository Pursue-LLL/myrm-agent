"""A background job asks a question and the model answers it through the real process tool.

The bash tool tells the model that a foreground prompt cannot be answered and that an interactive program runs with
``run_in_background`` and takes its reply from ``bash_process_tool``. This is that route on a real child. The job runs
on a pseudo-terminal when the host applies no OS sandbox and on plain pipes when it does; the reply reaches the
program's ``input()`` either way.
"""

from __future__ import annotations

import sys

import pytest

from myrm_agent_harness.toolkits.code_execution.executors.local import _background_pty_spawn
from tests.agent.meta_tools.bash.real_stack import RealBashStack

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX pseudo-terminals")

_ASK_AND_GREET = "import sys\nprint('tty', sys.stdin.isatty())\nname = input('name? ')\nprint('hi', name)\n"


@pytest.mark.parametrize("on_pty", [True, False], ids=["pty", "pipes"])
async def test_a_background_job_receives_the_reply_the_model_submits(
    shared_real_stack: RealBashStack, monkeypatch: pytest.MonkeyPatch, on_pty: bool
) -> None:
    if not on_pty:
        monkeypatch.setattr(_background_pty_spawn, "pty_spawn_eligible", lambda *, sandbox_enabled: False)
    (shared_real_stack.workspace / "ask.py").write_text(_ASK_AND_GREET, encoding="utf-8")

    job = await shared_real_stack.run_background("python3 ask.py", reply="Ada")

    assert job.exit_code == 0
    assert f"tty {on_pty}" in job.stdout
    assert "hi Ada" in job.stdout
