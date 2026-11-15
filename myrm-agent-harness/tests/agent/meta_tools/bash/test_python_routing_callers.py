"""One command, three callers, one route.

The executor, the bash tool's own checks and the permission layer each ask ``code_detector`` how a command will run,
and each acts on the answer: text run as Python gets Python's rules, text a shell reads gets the shell's. If one of
them answered differently, a command would be judged under one language and run under the other. Every command below
is one the old line-count and keyword router got wrong, and every test reads a caller's own consequence of the route.
(The reserved-import preflight asks the same detector but blocks the same text under either route, so it has no
route-dependent behavior to compare.)
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.agent.meta_tools.bash._executor.error import BashExecutionError
from myrm_agent_harness.agent.meta_tools.bash._executor.executor import BashExecutor
from myrm_agent_harness.agent.meta_tools.bash.bash_code_execute_tool import create_bash_code_execute_tool
from myrm_agent_harness.agent.security.checks import check_shell_threats
from myrm_agent_harness.agent.skills.mcp.ipc_proxy import CallerScope
from myrm_agent_harness.core.security.types import PermissionAction
from myrm_agent_harness.utils.errors import ToolError
from tests.agent.meta_tools.bash.test_bash_tool import _patch_bash_tool_deps

# Short Python (the old router sent anything of three lines or fewer to the shell).
PYTHON_BITWISE_AND = "flags = 6 & 3\nprint(flags)"
PYTHON_REGEX_ANCHOR = "import re\nprint(re.match(r'^v$', 'v'))"
# Shell that names a Python keyword in a string (the old router sent any text containing ``await`` to Python).
SHELL_DETACHED_AMPERSAND = 'grep -rn "await" src/ & echo started'
SHELL_ANSI_C_QUOTING = "grep -rn \"await\" src/ && echo $'done'"


async def _executor_runs_python(command: str) -> bool:
    executor = MagicMock()
    executor.config = MagicMock()
    bash_executor = BashExecutor(executor, enable_skill_execution=False)
    async with AsyncExitStack() as ipc_servers:
        prepared = await bash_executor._prepare_execution(command, CallerScope(session_id="s1"), ipc_servers)
    return prepared.use_python_execution


@pytest.mark.parametrize(
    ("command", "python"),
    [
        pytest.param(PYTHON_BITWISE_AND, True, id="python-bitwise-and"),
        pytest.param(PYTHON_REGEX_ANCHOR, True, id="python-regex-anchor"),
        pytest.param(SHELL_DETACHED_AMPERSAND, False, id="shell-detached-ampersand"),
        pytest.param(SHELL_ANSI_C_QUOTING, False, id="shell-ansi-c-quoting"),
    ],
)
async def test_the_executor_runs_the_text_in_the_language_the_callers_judged_it_in(command: str, python: bool) -> None:
    assert await _executor_runs_python(command) is python


async def test_the_tool_lets_python_use_an_ampersand_and_refuses_a_detached_shell_job() -> None:
    mock_bash_exec, p_ctx, p_get, p_be, p_scope = _patch_bash_tool_deps()
    mock_bash_exec.execute.side_effect = BashExecutionError("reached the executor", phase="execution")

    with p_ctx, p_get, p_be, p_scope:
        tool = create_bash_code_execute_tool()
        with pytest.raises(ToolError) as reached:
            await tool.ainvoke({"command": PYTHON_BITWISE_AND, "reason": "mask two flags"})
        mock_bash_exec.execute.assert_awaited_once()
        assert "Detached background" not in str(reached.value)

        with pytest.raises(ToolError, match="Detached background"):
            await tool.ainvoke({"command": SHELL_DETACHED_AMPERSAND, "reason": "start a job"})
        mock_bash_exec.execute.assert_awaited_once()


def test_the_permission_layer_reads_a_regex_anchor_in_python_but_not_in_a_shell() -> None:
    assert check_shell_threats("code_interpreter", {"command": PYTHON_REGEX_ANCHOR}) == (None, "")

    action, reason = check_shell_threats("code_interpreter", {"command": SHELL_ANSI_C_QUOTING})
    assert action == PermissionAction.DENY
    assert "ANSI-C quoting" in reason
