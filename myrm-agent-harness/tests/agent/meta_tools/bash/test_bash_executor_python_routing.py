"""Integration tests: BashExecutor._prepare_execution routes via toolkits code_detector."""

from contextlib import AsyncExitStack
from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.agent.meta_tools.bash._executor.executor import (
    BashExecutionError,
    BashExecutor,
)
from myrm_agent_harness.agent.skills.mcp.ipc_proxy import CallerScope
from myrm_agent_harness.toolkits.code_execution import MCPConfigItem


@pytest.fixture
def bash_executor() -> BashExecutor:
    mock_code_executor = MagicMock()
    mock_code_executor.config = MagicMock()
    return BashExecutor(mock_code_executor, enable_skill_execution=False)


async def _prepare(bash_executor: BashExecutor, command: str) -> tuple[bool, str, object, str | None]:
    async with AsyncExitStack() as ipc_servers:
        return await bash_executor._prepare_execution(command, CallerScope(session_id="s1"), ipc_servers)


class TestPrepareExecutionPythonRouting:
    async def test_bash_command_stays_bash_mode(self, bash_executor: BashExecutor) -> None:
        use_python, prepared, mcp, _ = await _prepare(bash_executor, "ls -la")
        assert use_python is False
        assert prepared == "ls -la"
        assert mcp is None

    async def test_python_c_extracts_and_enables_python_mode(self, bash_executor: BashExecutor) -> None:
        use_python, prepared, mcp, _ = await _prepare(bash_executor, 'python3 -c "print(1)"')
        assert use_python is True
        assert prepared == "print(1)"
        assert mcp is None
        assert bash_executor.consume_python_c_transform_hint() is not None

    async def test_multiline_python_enables_python_mode(self, bash_executor: BashExecutor) -> None:
        code = "import os\nimport sys\n\ndef main():\n    pass\nmain()"
        use_python, prepared, _, _ = await _prepare(bash_executor, code)
        assert use_python is True
        assert prepared == code

    async def test_invalid_python_raises_before_executor(self, bash_executor: BashExecutor) -> None:
        with pytest.raises(BashExecutionError) as exc_info:
            await _prepare(bash_executor, 'python3 -c "def broken("')
        assert exc_info.value.phase == "preparation"

    async def test_await_async_python(self, bash_executor: BashExecutor) -> None:
        use_python, prepared, _, _ = await _prepare(bash_executor, "result = await fetch()")
        assert use_python is True
        assert "await" in prepared

    async def test_top_level_await_passes_preflight_syntax_validation(self, bash_executor: BashExecutor) -> None:
        code = "import asyncio\nres = await fetch_something()\nprint(res)"
        use_python, prepared, _, _ = await _prepare(bash_executor, code)
        assert use_python is True
        assert "await" in prepared

    async def test_top_level_async_for_with_future_annotations_passes_preflight(
        self, bash_executor: BashExecutor
    ) -> None:
        code = (
            "from __future__ import annotations\nimport sys\nimport os\nasync for row in async_iter():\n    print(row)"
        )
        use_python, prepared, _, _ = await _prepare(bash_executor, code)
        assert use_python is True
        assert "async for" in prepared

    def test_mcp_timeout_floor_applied(self, bash_executor: BashExecutor) -> None:
        from myrm_agent_harness.agent.meta_tools.bash._executor.constants import MCP_MIN_TIMEOUT

        short_limit_server = MCPConfigItem(name="demo", execute_timeout=10.0)
        assert bash_executor._maybe_extend_timeout_for_mcp([short_limit_server], 30) == MCP_MIN_TIMEOUT
        assert bash_executor._maybe_extend_timeout_for_mcp(None, 600) == 600
