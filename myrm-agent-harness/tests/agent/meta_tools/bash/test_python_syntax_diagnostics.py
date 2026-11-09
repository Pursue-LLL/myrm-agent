"""A syntax error in the model's Python is reported against the model's own lines, whatever runs before them."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.agent.meta_tools.bash._executor.executor import BashExecutionError, BashExecutor
from myrm_agent_harness.agent.meta_tools.bash._executor.prepare_mixin import PreparedExecution
from myrm_agent_harness.agent.skills.mcp.executor import SkillExecutor
from myrm_agent_harness.agent.skills.mcp.ipc_proxy import CallerScope, IPCEndpoint

# Far longer than any script the model writes, so a line number counted from the top of the combined text is
# unmistakable.
CLIENT = "import os\n" * 60
ENDPOINT = IPCEndpoint(socket_path="/tmp/e.sock", tcp_port=0, auth_token="tok", trace_nonce="nonce-1")


@asynccontextmanager
async def _endpoint(scope: CallerScope) -> AsyncIterator[IPCEndpoint]:
    yield ENDPOINT


def _skill_executor(monkeypatch: pytest.MonkeyPatch, code: str) -> SkillExecutor:
    executor = SkillExecutor()
    monkeypatch.setattr(executor, "detect_skill_in_command", lambda _command: (True, "demo_skill"))
    monkeypatch.setattr(executor, "_extract_python_code", lambda _command: code)
    monkeypatch.setattr(executor, "get_skill_mcp_config", lambda _name: [MagicMock()])
    monkeypatch.setattr(executor, "_generate_mcp_client_code", lambda *args, **kwargs: CLIENT)
    monkeypatch.setattr(executor, "_collect_read_only_tools", lambda _name: frozenset())
    return executor


async def _prepare_skill_script(monkeypatch: pytest.MonkeyPatch, code: str) -> PreparedExecution:
    bash_exec = BashExecutor(MagicMock(), enable_skill_execution=True)
    bash_exec._skill_executor = _skill_executor(monkeypatch, code)
    prepare_mixin = "myrm_agent_harness.agent.meta_tools.bash._executor.prepare_mixin"
    with patch(f"{prepare_mixin}.mcp_ipc_endpoint", _endpoint):
        async with AsyncExitStack() as stack:
            return await bash_exec._prepare_execution("python3 -c 'x'", bash_exec._caller_scope("s1", "/ws"), stack)


async def test_skill_script_error_names_the_models_line_and_its_text(monkeypatch: pytest.MonkeyPatch) -> None:
    code = "import asyncio\nvalue = (1, 2\nprint(value)\n"

    with pytest.raises(BashExecutionError) as raised:
        await _prepare_skill_script(monkeypatch, code)

    assert raised.value.error_category == "syntax"
    assert str(raised.value).endswith("SyntaxError: '(' was never closed, line 2, column 9: `value = (1, 2`")


async def test_future_import_opening_a_skill_script_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    prepared = await _prepare_skill_script(monkeypatch, "from __future__ import annotations\nprint(1)\n")

    assert prepared.use_python_execution is True
    assert prepared.code.startswith(CLIENT)


async def test_plain_python_error_names_the_line_and_its_text() -> None:
    bash_exec = BashExecutor(MagicMock(), enable_skill_execution=False)

    with pytest.raises(BashExecutionError) as raised:
        async with AsyncExitStack() as stack:
            await bash_exec._prepare_execution(
                'python3 -c "import os\nx = (1,\nprint(x)"', CallerScope(session_id="s1"), stack
            )

    assert "line 2, column 5: `x = (1,`" in str(raised.value)
