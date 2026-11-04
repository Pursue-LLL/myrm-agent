"""MCP call markers through the production path, tool call to tool result.

Each hop here is the real one: ``bash_code_execute_tool`` -> ``BashExecutor`` (starts the execution's
IPC server, injects the generated client) -> a ``LocalExecutor`` subprocess -> ``ExecutionResult``
(output scrubbing) -> ``MCPMetadataExtractor``. Only the MCP server behind the connection is
replaced. The marker tests in this directory feed hand-built stdout straight to the extractor,
which is how a scrubber that truncated every real marker went unnoticed: the result of a
script that made a call was a garbled marker line, ``metadata`` was empty, and a script that
printed nothing returned none of its tool results.

A script saved to a file and started as ``python file.py`` is read by the host and runs through the same
path, limited to read-only MCP tools; any other way of starting it is left to the shell.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from myrm_agent_harness.agent.meta_tools.bash.bash_code_execute_tool import create_bash_code_execute_tool
from myrm_agent_harness.agent.skills.mcp.ipc_endpoint import mcp_ipc_endpoint
from myrm_agent_harness.agent.skills.mcp.ipc_proxy import CallerScope, IPCEndpoint
from myrm_agent_harness.agent.skills.runtime.registry import skill_registry
from myrm_agent_harness.backends.skills.types import MCPSkillData, SkillMetadata
from myrm_agent_harness.core.security.tool_registry.registry import (
    evict_skill_safety_metadata,
    register_ptc_safety_metadata,
)
from myrm_agent_harness.core.security.tool_registry.safety_table import SafetyMetadata
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.sandbox.providers.null import NullProvider
from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import SandboxStatus
from myrm_agent_harness.toolkits.code_execution.workspace.storage_root_bind import bind_workspace_storage_root
from myrm_agent_harness.utils.errors import ToolError

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Unix socket and heredoc semantics")

SECRET = "sk-proj-" + "a1B2c3D4" * 4
_TOOLS = ["list_pods", "leak_key", "delete_pod"]
_REASON = "verify the MCP marker channel end to end"
_SESSION = "marker-full-stack"


_MCP_CALLS: list[str] = []
"""Every tool the fake MCP server was asked to run, oldest first."""


async def _fake_mcp_call(server: str, tool: str, params: dict[str, object]) -> tuple[dict[str, str], None]:
    _MCP_CALLS.append(tool)
    if tool == "delete_pod":
        return {"type": "text", "text": json.dumps({"deleted": params.get("name")})}, None
    if tool == "list_pods":
        pods = [{"name": f"api-{i:03d}", "status": "CrashLoopBackOff" if i % 3 == 0 else "Running"} for i in range(40)]
        return {"type": "text", "text": json.dumps({"pods": pods})}, None
    return {"type": "text", "text": json.dumps({"api_key": SECRET})}, None


_ENDPOINTS: list[IPCEndpoint] = []
"""The IPC server of every execution the tool has run, oldest first (each is gone once its run ends)."""
_SCOPES: list[CallerScope] = []
"""The caller scope each of those servers was started with."""


@asynccontextmanager
async def _recording_endpoint(scope: CallerScope) -> AsyncIterator[IPCEndpoint]:
    async with mcp_ipc_endpoint(scope) as endpoint:
        _ENDPOINTS.append(endpoint)
        _SCOPES.append(scope)
        yield endpoint


@pytest.fixture
async def tool(tmp_path: Path) -> AsyncIterator[BaseTool]:
    _ENDPOINTS.clear()
    _SCOPES.clear()
    _MCP_CALLS.clear()
    skill_registry.clear()
    register_ptc_safety_metadata(
        "mcp_demo_skill", "list_pods", SafetyMetadata(is_read_only=True), {"readOnlyHint": True}
    )
    skill_registry.register(
        SkillMetadata(
            name="mcp_demo_skill",
            description="demo",
            mcp=MCPSkillData(
                server="demo",
                tools=_TOOLS,
                config=[{"name": "demo", "type": "stdio", "command": "echo"}],
                tool_schemas={name: {"inputSchema": {"type": "object", "properties": {}}} for name in _TOOLS},
            ),
        )
    )
    connection = MagicMock()
    connection.call = AsyncMock(side_effect=_fake_mcp_call)
    manager = MagicMock()
    manager.get_connection = AsyncMock(return_value=connection)

    no_sandbox = (NullProvider(), SandboxStatus(enabled=False, provider_name="null", reason="test"))
    executor = LocalExecutor(ExecutionConfig())
    executor.bind_workspace(str(tmp_path))
    token = set_executor(executor)
    bind_workspace_storage_root(tmp_path)
    with (
        patch(
            "myrm_agent_harness.toolkits.code_execution.sandbox.detector.detect_sandbox_provider",
            return_value=no_sandbox,
        ),
        patch("myrm_agent_harness.toolkits.code_execution.sandbox.detect_sandbox_provider", return_value=no_sandbox),
        patch("myrm_agent_harness.utils.event_utils.dispatch_custom_event", AsyncMock()),
        patch(
            "myrm_agent_harness.toolkits.mcp.connection_manager.get_mcp_connection_manager",
            AsyncMock(return_value=manager),
        ),
        patch("myrm_agent_harness.agent.meta_tools.bash._executor.prepare_mixin.mcp_ipc_endpoint", _recording_endpoint),
    ):
        yield create_bash_code_execute_tool()
    reset_executor(token)
    skill_registry.clear()
    evict_skill_safety_metadata("mcp_demo_skill")


def _config(tmp_path: Path) -> RunnableConfig:
    return {
        "configurable": {
            "context": {
                "session_id": _SESSION,
                "workspace_path": str(tmp_path),
                "workspaces_storage_root": str(tmp_path),
            }
        }
    }


def _script(body: str) -> str:
    imports = "import asyncio\nfrom skills.mcp_demo_skill import list_pods, leak_key\n"
    return f"python3 << 'PYEOF'\n{imports}async def main():\n{body}\nasyncio.run(main())\nPYEOF\n"


async def _run(tool: BaseTool, tmp_path: Path, body: str) -> dict[str, object]:
    result = await tool.ainvoke({"command": _script(body), "reason": _REASON}, config=_config(tmp_path))
    assert isinstance(result, dict)
    return result


def _sources(out: dict[str, object]) -> list[dict[str, object]]:
    metadata = out["metadata"]
    assert isinstance(metadata, dict)
    sources = metadata["sources"]
    assert isinstance(sources, list)
    return sources


def _calls(source: dict[str, object]) -> list[dict[str, str]]:
    calls = source["calls"]
    assert isinstance(calls, list)
    return calls


@pytest.mark.asyncio
async def test_a_printing_script_returns_its_output_and_its_calls_become_sources(
    tool: BaseTool, tmp_path: Path
) -> None:
    out = await _run(tool, tmp_path, "    r = await list_pods()\n    print('pods:', len(r['pods']))")

    content = str(out["content"])
    assert "pods: 40" in content
    assert "__MCP_DATA__" not in content
    nonce = _ENDPOINTS[-1].trace_nonce
    assert nonce not in str(out), "the marker nonce must never reach the model"
    source = _sources(out)[0]
    assert source["skill_name"] == "mcp_demo_skill"
    assert [call["tool_name"] for call in _calls(source)] == ["list_pods"]
    assert "CrashLoopBackOff" in _calls(source)[0]["result_preview"]


@pytest.mark.asyncio
async def test_a_script_that_prints_nothing_returns_the_tool_result(tool: BaseTool, tmp_path: Path) -> None:
    out = await _run(tool, tmp_path, "    await list_pods()")

    content = str(out["content"])
    assert "[list_pods]" in content
    assert "CrashLoopBackOff" in content
    assert "__MCP_DATA__" not in content


@pytest.mark.asyncio
async def test_a_credential_in_a_tool_result_is_masked_in_output_and_sources(tool: BaseTool, tmp_path: Path) -> None:
    out = await _run(tool, tmp_path, "    await leak_key()")

    assert SECRET not in str(out)
    assert "api_key" in _calls(_sources(out)[0])[0]["result_preview"]


@pytest.mark.asyncio
async def test_a_failing_script_says_which_calls_already_ran_and_hides_the_marker(
    tool: BaseTool, tmp_path: Path
) -> None:
    with pytest.raises(ToolError) as excinfo:
        await _run(
            tool,
            tmp_path,
            "    await list_pods()\n    await list_pods()\n    raise RuntimeError('boom after two calls')",
        )

    message = str(excinfo.value)
    assert "RuntimeError: boom after two calls" in message
    assert "mcp_demo_skill.list_pods x2" in message
    assert "re-running them repeats their effects" in message
    assert "__MCP_DATA__" not in message
    nonce = _ENDPOINTS[-1].trace_nonce
    assert nonce not in message


@pytest.mark.asyncio
async def test_each_run_has_its_own_server_and_it_ends_with_the_run(tool: BaseTool, tmp_path: Path) -> None:
    await _run(tool, tmp_path, "    await list_pods()")
    with pytest.raises(ToolError):
        await _run(tool, tmp_path, "    await list_pods()\n    raise RuntimeError('boom')")

    first, second = _ENDPOINTS
    assert first.socket_path != second.socket_path
    assert first.trace_nonce != second.trace_nonce
    assert not os.path.exists(first.socket_path), "a finished run leaves no server behind"
    assert not os.path.exists(second.socket_path), "nor does a failed one"


_SAVED_SCRIPT = """\
import asyncio
from skills.mcp_demo_skill import list_pods


async def main():
    r = await list_pods()
    print('pods:', len(r['pods']), __name__)


if __name__ == '__main__':
    asyncio.run(main())
"""


async def _run_command(tool: BaseTool, tmp_path: Path, command: str) -> dict[str, object]:
    result = await tool.ainvoke({"command": command, "reason": _REASON}, config=_config(tmp_path))
    assert isinstance(result, dict)
    return result


def _save(tmp_path: Path, source: str, name: str = "probe.py") -> None:
    """Write a script into the directory the executor is bound to, which is where the shell and ``/workspace`` point."""
    (tmp_path / name).write_text(source, encoding="utf-8")


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["python3 probe.py", "cd /workspace && python3 probe.py"])
async def test_a_saved_script_that_imports_a_skill_runs_with_the_skill_runtime(
    tool: BaseTool, tmp_path: Path, command: str
) -> None:
    _save(tmp_path, _SAVED_SCRIPT)

    out = await _run_command(tool, tmp_path, command)

    assert "pods: 40 __main__" in str(out["content"])
    assert "__MCP_DATA__" not in str(out["content"])
    assert _ENDPOINTS[-1].trace_nonce not in str(out), "the marker nonce must never reach the model"
    source = _sources(out)[0]
    assert source["skill_name"] == "mcp_demo_skill"
    assert [call["tool_name"] for call in _calls(source)] == ["list_pods"]
    assert _MCP_CALLS == ["list_pods"]


@pytest.mark.asyncio
async def test_a_saved_script_runs_under_a_scope_that_limits_it_to_read_only_tools(
    tool: BaseTool, tmp_path: Path
) -> None:
    _save(tmp_path, _SAVED_SCRIPT)

    await _run_command(tool, tmp_path, "python3 probe.py")
    await _run_command(tool, tmp_path, _script("    await list_pods()"))

    saved, inline = _SCOPES
    assert saved.script_file is True
    assert inline.script_file is False
    assert saved.workspace_root == inline.workspace_root


@pytest.mark.asyncio
async def test_a_saved_script_cannot_call_a_mutating_tool_but_inline_python_can(tool: BaseTool, tmp_path: Path) -> None:
    _save(
        tmp_path,
        "import asyncio\nfrom skills.mcp_demo_skill import delete_pod\nasyncio.run(delete_pod(name='api-001'))\n",
        "wipe.py",
    )

    with pytest.raises(ToolError) as excinfo:
        await _run_command(tool, tmp_path, "python3 wipe.py")

    message = str(excinfo.value)
    assert "saved script" in message
    assert "inline Python" in message
    assert _MCP_CALLS == [], "the mutating tool must never reach the MCP server from a saved script"

    inline = "import asyncio\nfrom skills.mcp_demo_skill import delete_pod\nasyncio.run(delete_pod(name='api-001'))"
    await _run_command(tool, tmp_path, f"python3 << 'PYEOF'\n{inline}\nPYEOF\n")
    assert _MCP_CALLS == ["delete_pod"]


@pytest.mark.asyncio
async def test_a_failing_saved_script_names_its_file_and_the_calls_that_already_ran(
    tool: BaseTool, tmp_path: Path
) -> None:
    _save(
        tmp_path,
        "import asyncio\nfrom skills.mcp_demo_skill import list_pods\n"
        "asyncio.run(list_pods())\nraise RuntimeError('boom after one call')\n",
        "fails.py",
    )

    with pytest.raises(ToolError) as excinfo:
        await _run_command(tool, tmp_path, "python3 fails.py")

    message = str(excinfo.value)
    assert "RuntimeError: boom after one call" in message
    assert "mcp_demo_skill.list_pods x1" in message
    assert "fails.py" in message
    assert "__MCP_DATA__" not in message


@pytest.mark.asyncio
async def test_a_saved_script_without_a_skill_import_runs_as_a_plain_command(tool: BaseTool, tmp_path: Path) -> None:
    _save(tmp_path, "print('plain run')\n", "plain.py")

    out = await _run_command(tool, tmp_path, "python3 plain.py")

    assert "plain run" in str(out["content"])
    assert _ENDPOINTS == [], "no skill, no IPC server"


@pytest.mark.asyncio
async def test_a_saved_script_importing_the_projects_own_modules_is_not_taken_for_a_skill_call(
    tool: BaseTool, tmp_path: Path
) -> None:
    """``*_skill`` and ``tools`` are ordinary names in a project; only a skill the host serves is routed."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "tools" / "helpers.py").write_text("def run():\n    return 'local tools'\n", encoding="utf-8")
    (tmp_path / "data_skill.py").write_text("VALUE = 'local data_skill'\n", encoding="utf-8")
    _save(tmp_path, "from tools.helpers import run\nimport data_skill\nprint(run(), data_skill.VALUE)\n", "local.py")

    out = await _run_command(tool, tmp_path, "python3 local.py")

    assert "local tools local data_skill" in str(out["content"])
    assert _ENDPOINTS == []


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["python3 probe.py --x", "python3 -u probe.py", "python3 probe.py | cat"])
async def test_other_ways_of_starting_a_saved_script_are_left_to_the_shell(
    tool: BaseTool, tmp_path: Path, command: str
) -> None:
    _save(tmp_path, _SAVED_SCRIPT)

    out = await _run_command(tool, tmp_path, command)

    assert "No module named 'skills'" in str(out["content"])
    assert _ENDPOINTS == []
    assert _MCP_CALLS == []


@pytest.mark.asyncio
async def test_a_saved_script_that_does_not_parse_is_reported_by_python(tool: BaseTool, tmp_path: Path) -> None:
    _save(tmp_path, "from skills.mcp_demo_skill import list_pods\nif x ==\n", "broken.py")

    out = await _run_command(tool, tmp_path, "python3 broken.py")

    assert "SyntaxError" in str(out["content"])
    assert _ENDPOINTS == []
