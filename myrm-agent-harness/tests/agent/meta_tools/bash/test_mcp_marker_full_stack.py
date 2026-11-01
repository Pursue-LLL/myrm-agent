"""MCP call markers through the production path, tool call to tool result.

Each hop here is the real one: ``bash_code_execute_tool`` -> ``BashExecutor`` (starts the IPC
server, injects the generated client) -> a ``LocalExecutor`` subprocess -> ``ExecutionResult``
(output scrubbing) -> ``MCPMetadataExtractor``. Only the MCP server behind the connection is
replaced. The marker tests in this directory feed hand-built stdout straight to the extractor,
which is how a scrubber that truncated every real marker went unnoticed: the result of a
script that made a call was a garbled marker line, ``metadata`` was empty, and a script that
printed nothing returned none of its tool results.
"""

from __future__ import annotations

import json
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.tools import BaseTool

from myrm_agent_harness.agent.meta_tools.bash.bash_code_execute_tool import create_bash_code_execute_tool
from myrm_agent_harness.agent.skills.mcp.ipc_proxy import get_mcp_trace_nonce, stop_mcp_ipc_server
from myrm_agent_harness.agent.skills.runtime.registry import skill_registry
from myrm_agent_harness.backends.skills.types import MCPSkillData, SkillMetadata
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.sandbox.providers.null import NullProvider
from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import SandboxStatus
from myrm_agent_harness.toolkits.code_execution.workspace.storage_root_bind import bind_workspace_storage_root
from myrm_agent_harness.utils.errors import ToolError

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Unix socket and heredoc semantics")

SECRET = "sk-proj-" + "a1B2c3D4" * 4
_TOOLS = ["list_pods", "leak_key"]
_REASON = "verify the MCP marker channel end to end"


async def _fake_mcp_call(server: str, tool: str, params: dict[str, object]) -> tuple[dict[str, str], None]:
    if tool == "list_pods":
        pods = [{"name": f"api-{i:03d}", "status": "CrashLoopBackOff" if i % 3 == 0 else "Running"} for i in range(40)]
        return {"type": "text", "text": json.dumps({"pods": pods})}, None
    return {"type": "text", "text": json.dumps({"api_key": SECRET})}, None


@pytest.fixture
async def tool(tmp_path: Path) -> AsyncIterator[BaseTool]:
    skill_registry.clear()
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
    ):
        yield create_bash_code_execute_tool()
    await stop_mcp_ipc_server()
    reset_executor(token)
    skill_registry.clear()


def _config(tmp_path: Path) -> dict[str, object]:
    return {
        "configurable": {
            "context": {
                "session_id": "marker-full-stack",
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
    nonce = get_mcp_trace_nonce()
    assert nonce is not None
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
    nonce = get_mcp_trace_nonce()
    assert nonce is not None
    assert nonce not in message
