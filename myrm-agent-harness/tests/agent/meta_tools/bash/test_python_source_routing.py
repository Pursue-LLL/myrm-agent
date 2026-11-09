"""Shell-only guards stand down for Python source the wrapper runs, and nowhere a shell reads the text.

The bash tool takes Python source directly. Its wrapper runs that source without a shell, so ``a & b`` is a
bitwise operator and ``r'^v$'`` is a regex anchor. A text that a shell does read (a background spawn, a
whitelisted build/test command that is auto-yielded into one) keeps every guard.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.agent.meta_tools.bash._executor.auto_yield import should_auto_yield
from myrm_agent_harness.agent.meta_tools.bash._executor.error import BashExecutionError
from myrm_agent_harness.agent.meta_tools.bash._executor.executor import BashExecutor
from myrm_agent_harness.agent.meta_tools.bash.bash_code_execute_tool import create_bash_code_execute_tool
from myrm_agent_harness.toolkits.code_execution.code_detector import runs_as_python
from myrm_agent_harness.utils.errors import ToolError
from tests.agent.meta_tools.bash.test_background_ampersand_guard import _mock_executor
from tests.agent.meta_tools.bash.test_bash_tool import _patch_bash_tool_deps

SET_INTERSECTION = "\n".join(
    (
        "import json",
        "staging = {'api', 'web'}",
        "prod = {'api', 'db'}",
        "for name in sorted(staging & prod):",
        "    print(json.dumps(name))",
    )
)
# Same source, but it names a whitelisted build/test command, which makes the bash tool spawn it in a shell.
SET_INTERSECTION_NAMING_PYTEST = SET_INTERSECTION.replace("import json", "import json  # then run pytest")
# A regex end anchor followed by a quote, in text that also names a whitelisted build/test command.
ANCHORED_REGEX_NAMING_PYTEST = "\n".join(
    (
        "import re",
        "# then run pytest",
        "for tag in ['v1', 'v2']:",
        "    print(re.match(r'^v(\\d+)$', tag), 'x')",
        "print('done')",
    )
)


@pytest.mark.asyncio
async def test_python_source_with_a_bitwise_and_reaches_the_executor() -> None:
    mock_bash_exec, p_ctx, p_get, p_be, p_scope = _patch_bash_tool_deps()
    mock_bash_exec.execute.side_effect = BashExecutionError("reached the executor", phase="execution")

    with p_ctx, p_get, p_be, p_scope:
        tool = create_bash_code_execute_tool()
        with pytest.raises(ToolError) as exc_info:
            await tool.ainvoke({"command": SET_INTERSECTION, "reason": "intersect two sets"})

    mock_bash_exec.execute.assert_awaited_once()
    assert "Detached background" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_a_shell_command_with_a_detached_ampersand_is_still_refused() -> None:
    mock_bash_exec, p_ctx, p_get, p_be, p_scope = _patch_bash_tool_deps()

    with p_ctx, p_get, p_be, p_scope:
        tool = create_bash_code_execute_tool()
        with pytest.raises(ToolError, match="Detached background"):
            await tool.ainvoke({"command": "npm run dev & echo started", "reason": "start the dev server"})

    mock_bash_exec.execute.assert_not_called()


@pytest.mark.asyncio
async def test_python_source_that_a_shell_will_read_keeps_the_ampersand_guard() -> None:
    assert should_auto_yield(command=SET_INTERSECTION_NAMING_PYTEST, run_in_background=False, yield_after_seconds=None)
    mock_bash_exec, p_ctx, p_get, p_be, p_scope = _patch_bash_tool_deps()

    with p_ctx, p_get, p_be, p_scope:
        tool = create_bash_code_execute_tool()
        with pytest.raises(ToolError, match="Detached background"):
            await tool.ainvoke({"command": SET_INTERSECTION_NAMING_PYTEST, "reason": "intersect two sets"})

    mock_bash_exec.execute.assert_not_called()
    mock_bash_exec.spawn_background.assert_not_called()


@pytest.mark.asyncio
async def test_spawn_background_judges_the_text_the_shell_is_about_to_read() -> None:
    """The permission engine reads this text as Python and skips shell quoting; the spawn must not."""
    command = ANCHORED_REGEX_NAMING_PYTEST
    assert runs_as_python(command)
    assert should_auto_yield(command=command, run_in_background=False, yield_after_seconds=None)

    executor = _mock_executor()
    executor.spawn_background_process = AsyncMock()
    bash_exec = BashExecutor(executor, enable_skill_execution=False)

    with pytest.raises(BashExecutionError, match=r"Locale quoting|ANSI-C") as exc_info:
        await bash_exec.spawn_background(command, session_id="sess-1")

    assert exc_info.value.error_category == "SHELL_THREAT"
    executor.spawn_background_process.assert_not_awaited()
