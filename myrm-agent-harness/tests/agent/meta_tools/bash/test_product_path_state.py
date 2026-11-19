"""What one bash call leaves for the next, through the real bash tool and a real shell.

The tool description tells the model to treat every call as a fresh start and to put ``cd dir && command`` into one
call. These cases are the evidence for those two sentences: the directory and the variables or functions a call sets
are gone for the next call, and a combined call keeps them to its end. If the session starts to carry state across
calls, the description changes together with these cases.
"""

from __future__ import annotations

import sys

import pytest

from tests.agent.meta_tools.bash.real_stack import RealBashStack

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell semantics")

_TIMEOUT = 10
_SUBDIRECTORY = "state-probe-subdirectory"


async def test_cd_and_the_command_in_one_call_run_in_that_directory(real_stack: RealBashStack) -> None:
    (real_stack.workspace / _SUBDIRECTORY).mkdir()

    output = await real_stack.run(f'cd {_SUBDIRECTORY} && basename "$PWD"', timeout=_TIMEOUT)

    assert _SUBDIRECTORY in output


async def test_the_next_call_starts_in_the_workspace_root(real_stack: RealBashStack) -> None:
    (real_stack.workspace / _SUBDIRECTORY).mkdir()
    await real_stack.run(f"cd {_SUBDIRECTORY}", timeout=_TIMEOUT)

    output = await real_stack.run('basename "$PWD"', timeout=_TIMEOUT)

    assert real_stack.workspace.name in output
    assert _SUBDIRECTORY not in output


_STATE_CASES = [
    pytest.param(
        "export MYRM_STATE_PROBE=1",
        'test -n "$MYRM_STATE_PROBE" && echo kept || echo gone',
        id="export",
    ),
    pytest.param(
        "myrm_state_probe() {\n  true\n}",
        "type myrm_state_probe >/dev/null 2>&1 && echo kept || echo gone",
        id="function",
    ),
]


@pytest.mark.parametrize(("set_up", "probe"), _STATE_CASES)
async def test_the_probe_sees_state_set_in_the_same_call(real_stack: RealBashStack, set_up: str, probe: str) -> None:
    assert "kept" in await real_stack.run(f"{set_up}\n{probe}", timeout=_TIMEOUT)


@pytest.mark.parametrize(("set_up", "probe"), _STATE_CASES)
async def test_a_variable_or_function_does_not_reach_the_next_call(
    real_stack: RealBashStack, set_up: str, probe: str
) -> None:
    await real_stack.run(set_up, timeout=_TIMEOUT)

    output = await real_stack.run(probe, timeout=_TIMEOUT)

    assert "gone" in output
    assert "kept" not in output
