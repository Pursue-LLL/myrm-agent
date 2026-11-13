"""A failed MCP call reaches a Python script as an exception, inside the limit the server is configured with.

Everything between the script and the server is the production path: ``bash_code_execute_tool`` -> host -> generated client
-> IPC -> proxy service -> connection manager -> session actor -> a real stdio MCP server (the cancel-probe server). Only the
limits are shrunk to seconds. Each test pins a behavior that used to go the other way:

- a hung tool: the script was handed the actor's timeout *text as the call's return value*, and a read cache then kept
  that text as if it were a result;
- the host kill: the script's own deadline was equal to the actor's, so the host could end the script before the named
  error reached it;
- a cold start: a bound on the whole request would charge the server's start-up to a call that is within its limit;
- an ended script: its call kept occupying the MCP server until the tool's own limit, so the next script waited for it.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from myrm_agent_harness.agent.meta_tools.bash.bash_code_execute_tool import create_bash_code_execute_tool
from myrm_agent_harness.agent.skills.runtime.registry import skill_registry
from myrm_agent_harness.backends.skills.types import MCPSkillData, SkillMetadata
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.sandbox.providers.null import NullProvider
from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import SandboxStatus
from myrm_agent_harness.toolkits.code_execution.workspace.storage_root_bind import bind_workspace_storage_root
from myrm_agent_harness.toolkits.mcp.connection_manager import MCPConnectionManager
from myrm_agent_harness.utils.errors import ToolError
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, CancelReason, set_cancel_token
from tests.support.marked_processes import wait_until
from tests.support.mcp_testkit import cancel_probe_server

pytestmark = [
    pytest.mark.skipif(sys.platform == "win32", reason="Unix socket and heredoc semantics"),
    pytest.mark.slow,
]

_HOST_FLOOR = "myrm_agent_harness.agent.meta_tools.bash._executor.prepare_mixin.MCP_MIN_TIMEOUT"
_BACKSTOP_MARGIN = "myrm_agent_harness.agent.skills.mcp.call_backstop.BACKSTOP_MARGIN_SECONDS"
_REASON = "verify how a failed MCP call reaches a script"
_TOOLS = ["slow", "fast"]
_SLOW_FOREVER_S = 60
# Bound on waiting for an event that is bound to happen: the wait returns the moment it does, and the bound stays under
# the host's own 120 s floor so a stuck stack fails here, with a clear message, before the host's deadline does.
_EVENT_WAIT_S = 60

_DELAYED_START = (
    "import runpy, sys, time; time.sleep(float(sys.argv[1])); "
    "sys.argv = [sys.argv[2], sys.argv[3]]; runpy.run_path(sys.argv[0], run_name='__main__')"
)


def _server_config(marks: Path, *, execute_timeout: float, cache: bool, start_delay: float) -> dict[str, object]:
    server_file = cancel_probe_server.__file__
    args = (
        ["-c", _DELAYED_START, str(start_delay), server_file, str(marks)] if start_delay else [server_file, str(marks)]
    )
    return {
        "name": "cancelprobe",
        "type": "stdio",
        "command": sys.executable,
        "args": args,
        "description": "cancel probe",
        "connect_timeout": 30.0,
        "execute_timeout": execute_timeout,
        **({"cache_ttl_seconds": 60, "cacheable_tools": ["slow"]} if cache else {}),
    }


@asynccontextmanager
async def _script_channel(
    tmp_path: Path, *, execute_timeout: float, cache: bool = False, start_delay: float = 0.0
) -> AsyncIterator[BaseTool]:
    """The bash tool, wired to a skill whose MCP server is the real cancel-probe process."""
    MCPConnectionManager._instance = None
    marks = tmp_path / "marks"
    marks.mkdir()
    skill_registry.clear()
    skill_registry.register(
        SkillMetadata(
            name="mcp_demo_skill",
            description="demo",
            mcp=MCPSkillData(
                server="cancelprobe",
                tools=_TOOLS,
                config=[_server_config(marks, execute_timeout=execute_timeout, cache=cache, start_delay=start_delay)],
                tool_schemas={
                    "slow": {
                        "inputSchema": {
                            "type": "object",
                            "properties": {"seconds": {"type": "number"}},
                            "required": ["seconds"],
                        }
                    },
                    "fast": {"inputSchema": {"type": "object", "properties": {}}},
                },
            ),
        )
    )
    no_sandbox = (NullProvider(), SandboxStatus(enabled=False, provider_name="null", reason="test"))
    executor = LocalExecutor(ExecutionConfig())
    executor.bind_workspace(str(tmp_path))
    token = set_executor(executor)
    bind_workspace_storage_root(tmp_path)
    try:
        with (
            patch(
                "myrm_agent_harness.toolkits.code_execution.sandbox.detector.detect_sandbox_provider",
                return_value=no_sandbox,
            ),
            patch(
                "myrm_agent_harness.toolkits.code_execution.sandbox.detect_sandbox_provider",
                return_value=no_sandbox,
            ),
            patch("myrm_agent_harness.utils.event_utils.dispatch_custom_event", AsyncMock()),
        ):
            yield create_bash_code_execute_tool()
    finally:
        manager = MCPConnectionManager._instance
        if manager is not None:
            with contextlib.suppress(Exception):
                await manager.stop()
        MCPConnectionManager._instance = None
        reset_executor(token)
        skill_registry.clear()


def _config(tmp_path: Path) -> RunnableConfig:
    return {
        "configurable": {
            "context": {
                "session_id": "script-failure-contract",
                "workspace_path": str(tmp_path),
                "workspaces_storage_root": str(tmp_path),
            }
        }
    }


def _python_script(body: str) -> str:
    imports = "import asyncio, time\nfrom skills.mcp_demo_skill import fast, slow\n"
    return f"python3 << 'PYEOF'\n{imports}async def main():\n{body}\nasyncio.run(main())\nPYEOF\n"


def _call_slow(seconds: float, label: str) -> str:
    """Script lines: one ``slow`` call whose outcome (returned value or raised error) is printed under ``label``."""
    return (
        "    t = time.time()\n"
        "    try:\n"
        f"        r = await slow(seconds={seconds})\n"
        f"        print('{label} RETURNED %r after %.1fs' % (str(r)[:80], time.time() - t), flush=True)\n"
        "    except Exception as e:\n"
        f"        print('{label} RAISED after %.1fs: %s' % (time.time() - t, str(e)[:160]), flush=True)\n"
    )


async def _run(tool: BaseTool, tmp_path: Path, body: str) -> list[str]:
    """Run the script and return its output lines."""
    result = await tool.ainvoke({"command": _python_script(body), "reason": _REASON}, config=_config(tmp_path))
    assert isinstance(result, dict)
    return str(result["content"]).splitlines()


def _outcome(lines: list[str], label: str) -> str:
    matching = [line for line in lines if line.startswith(f"{label} ")]
    assert len(matching) == 1, f"expected one '{label}' line in {lines}"
    return matching[0]


def _elapsed(line: str) -> float:
    match = re.search(r"after ([\d.]+)s", line)
    assert match is not None, line
    return float(match.group(1))


@pytest.mark.asyncio
async def test_a_tool_that_hangs_raises_in_the_script_instead_of_returning_its_timeout_text(tmp_path: Path) -> None:
    async with _script_channel(tmp_path, execute_timeout=2.0) as tool:
        with patch(_HOST_FLOOR, 40):
            lines = await _run(tool, tmp_path, _call_slow(_SLOW_FOREVER_S, "hang") + "    print('after', await fast())")

    outcome = _outcome(lines, "hang")
    assert "RAISED" in outcome, f"the script was handed an error as the call's value: {outcome}"
    assert "timed out after 2.0s" in outcome
    assert any(line.startswith("after") and "fast-done" in line for line in lines), "the next call must still work"


@pytest.mark.asyncio
async def test_a_failure_is_not_served_again_from_the_read_cache(tmp_path: Path) -> None:
    async with _script_channel(tmp_path, execute_timeout=2.0, cache=True) as tool:
        with patch(_HOST_FLOOR, 40):
            lines = await _run(
                tool, tmp_path, _call_slow(_SLOW_FOREVER_S, "first") + _call_slow(_SLOW_FOREVER_S, "second")
            )

    first, second = _outcome(lines, "first"), _outcome(lines, "second")
    assert "RAISED" in first
    assert "RAISED" in second, f"the cached failure was served as a result: {second}"
    assert _elapsed(second) > 1.0, "the second call must run again, not come back from the cache"


@pytest.mark.asyncio
async def test_the_host_outlives_the_configured_limit_so_the_named_error_reaches_the_script(tmp_path: Path) -> None:
    started = time.monotonic()
    async with _script_channel(tmp_path, execute_timeout=6.0) as tool:
        # The host's own floor is far below the server's limit; it is the configured limit that must lift it.
        with patch(_HOST_FLOOR, 2):
            lines = await _run(tool, tmp_path, _call_slow(_SLOW_FOREVER_S, "hang"))

    outcome = _outcome(lines, "hang")
    assert "RAISED" in outcome
    assert "timed out after 6.0s" in outcome
    assert time.monotonic() - started < 30


@pytest.mark.asyncio
async def test_a_cold_start_is_not_charged_to_the_limit_of_a_call_that_is_within_it(tmp_path: Path) -> None:
    # Limit 3 s + margin 1 s = 4 s. The server needs 3.5 s to come up and the call takes 2 s: 5.5 s in all, 2 s of it the call.
    async with _script_channel(tmp_path, execute_timeout=3.0, start_delay=3.5) as tool:
        with patch(_HOST_FLOOR, 60), patch(_BACKSTOP_MARGIN, 1.0):
            lines = await _run(tool, tmp_path, _call_slow(2, "cold"))

    outcome = _outcome(lines, "cold")
    assert "RETURNED" in outcome and "slow-done" in outcome, f"a healthy call was cut by the start-up time: {outcome}"


@pytest.mark.asyncio
async def test_a_script_ended_by_the_host_frees_the_server_for_the_next_script(tmp_path: Path) -> None:
    marks = tmp_path / "marks"
    stop = CancellationToken("script-ended-contract")
    async with _script_channel(tmp_path, execute_timeout=25.0) as tool:
        # The host ends the first script while its call is still running. The stop comes once the server runs the call:
        # a deadline fixed up front counts from the script's start, so on a loaded machine it can fall before the server
        # is up and the call has reached it, and then there is no call to cancel. A stop and a deadline end the script
        # the same way (one process-group kill), so the abandoned call is released the same way.
        set_cancel_token(stop)
        first = asyncio.create_task(
            tool.ainvoke(
                {"command": _python_script(_call_slow(_SLOW_FOREVER_S, "hang")), "reason": _REASON},
                config=_config(tmp_path),
            )
        )
        try:
            await wait_until(lambda: (marks / cancel_probe_server.STARTED).exists(), timeout=_EVENT_WAIT_S)
            stop.cancel(CancelReason.USER_CANCELLED)
            with pytest.raises(ToolError):
                await asyncio.wait_for(first, timeout=_EVENT_WAIT_S)
        finally:
            set_cancel_token(None)
            first.cancel()
            await asyncio.gather(first, return_exceptions=True)
        ended = time.monotonic()

        lines = await _run(tool, tmp_path, "    print('next', await fast())")

    assert any("fast-done" in line for line in lines)
    assert time.monotonic() - ended < 12, "the next script waited for the abandoned call to reach its own limit"
    await wait_until(lambda: (marks / cancel_probe_server.CANCELLED).exists(), timeout=_EVENT_WAIT_S)
