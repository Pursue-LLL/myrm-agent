"""What an MCP PTC script observes when its call is malformed, end to end over the wire.

A call that omits a required argument used to come back as an error-shaped dict that
spoke Function-Calling ("tool_call", "arguments"), i.e. as a *successful* result. The
script then failed later on a ``KeyError`` far from the cause. The call must instead
raise, say what is missing, and show the signature to copy. An unknown tool must name
its nearest neighbours rather than the first five catalog entries.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.agent.skills.mcp.client_templates import generate_ipc_client_code
from myrm_agent_harness.agent.skills.mcp.ipc_proxy import MCPIPCServer
from myrm_agent_harness.agent.skills.runtime.registry import skill_registry
from myrm_agent_harness.backends.skills.types import MCPSkillData, SkillMetadata
from myrm_agent_harness.core.network.ipc_socket import default_ipc_socket_path

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Unix socket semantics")

_TOOLS = [f"decoy_tool_{i}" for i in range(8)] + ["create_issue"]


@pytest.fixture(autouse=True)
def _skill() -> Iterator[None]:
    skill_registry.clear()
    skill_registry.register(
        SkillMetadata(
            name="mcp_demo",
            description="demo",
            mcp=MCPSkillData(
                server="demo",
                tools=_TOOLS,
                config=[{"name": "demo", "type": "stdio", "command": "echo"}],
                tool_schemas={
                    "create_issue": {
                        "inputSchema": {
                            "type": "object",
                            "properties": {"title": {"type": "string"}, "body": {"type": "string"}},
                            "required": ["title"],
                        },
                    },
                },
            ),
        )
    )
    yield
    skill_registry.clear()


async def _run_script(user_code: str) -> tuple[str, MagicMock]:
    connection = MagicMock()
    connection.call = AsyncMock(return_value=({"type": "text", "text": "{}"}, None))
    manager = MagicMock()
    manager.get_connection = AsyncMock(return_value=connection)
    server = MCPIPCServer(default_ipc_socket_path())
    await server.start()
    try:
        client = generate_ipc_client_code(
            server.socket_path, session_id="chat_1", auth_token=server.auth_token, trace_nonce=server.trace_nonce
        )
        with patch(
            "myrm_agent_harness.toolkits.mcp.connection_manager.get_mcp_connection_manager",
            AsyncMock(return_value=manager),
        ):
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                f"{client}\n{user_code}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
        assert proc.returncode == 0, stderr.decode()
        return stdout.decode(), connection
    finally:
        await server.stop()


_CATCHING_SCRIPT = (
    "from skills.mcp_demo import {name}\n"
    "async def main():\n"
    "    try:\n"
    "        r = await {name}({args})\n"
    "        print('RETURNED', r)\n"
    "    except Exception as exc:\n"
    "        print('RAISED', type(exc).__name__, exc)\n"
    "asyncio.run(main())\n"
)


@pytest.mark.asyncio
async def test_missing_required_argument_raises_with_a_signature_and_never_reaches_the_server() -> None:
    stdout, connection = await _run_script(_CATCHING_SCRIPT.format(name="create_issue", args="body='x'"))

    assert "RETURNED" not in stdout, "a validation failure must not look like a successful result"
    assert "RAISED MCPError" in stdout
    assert "Missing required argument(s): title" in stdout
    assert "create_issue(*, title:string, body?:string)" in stdout
    assert "tool_call" not in stdout
    connection.call.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_tool_names_the_nearest_callable_even_when_it_is_deep_in_the_catalog() -> None:
    stdout, connection = await _run_script(_CATCHING_SCRIPT.format(name="create_isue", args="title='t'"))

    assert "RAISED MCPError" in stdout
    assert "Closest names: create_issue" in stdout
    connection.call.assert_not_called()
