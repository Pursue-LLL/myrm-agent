"""Live integration: real MCP server → skill generation → virtual /mcp/ doc read.

Exercises the production progressive-disclosure chain without mocks:

1. Boot a real streamable-http MCP server (4 tools > threshold 3).
2. Connect through ``MCPConnectionManager`` (real wire protocol).
3. Generate SkillMetadata from the real tools.
4. ``generate_skill_content`` — SKILL.md must carry the calling contract
   (``SKILL_USAGE_TEMPLATE``) unconditionally.
5. ``MCPFileSystemStrategy.read_file`` over ``/mcp/...`` — a tool whose required
   parameter carries an example gets an awaited call example built from it, a
   tool without one gets no placeholder call; a live ``conn.call`` proves the
   wire path.
"""

from __future__ import annotations

import asyncio
import socket
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Annotated

import pytest
from pydantic import Field
from starlette.applications import Starlette

from myrm_agent_harness.agent.meta_tools.file_ops.strategies.mcp_strategy import (
    MCPFileSystemStrategy,
)
from myrm_agent_harness.agent.skills.mcp.core_generator import SKILL_USAGE_TEMPLATE, MCPSkillGenerator
from myrm_agent_harness.toolkits.mcp.config import MCPConfig
from myrm_agent_harness.toolkits.mcp.connection_manager import MCPConnectionManager
from tests.support.sse_shutdown_flag import reset_sse_shutdown_flag


def _make_server_app() -> Starlette:
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("live-skill-probe")

    @server.tool()
    def echo(text: Annotated[str, Field(examples=["hello"])]) -> str:
        return f"echo:{text}"

    @server.tool()
    def add(a: int, b: int) -> int:
        return a + b

    @server.tool()
    def multiply(a: int, b: int) -> int:
        return a * b

    @server.tool()
    def get_status() -> str:
        return "ok"

    return server.streamable_http_app()


async def _start_live_server() -> tuple[Callable[[], Awaitable[None]], str]:
    import uvicorn

    app = _make_server_app()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    runner = uvicorn.Server(config)
    serve_task = asyncio.create_task(runner.serve(sockets=[sock]))
    for _ in range(200):
        if runner.started:
            break
        await asyncio.sleep(0.05)
    assert runner.started, "streamable-http server failed to start"

    async def teardown() -> None:
        runner.should_exit = True
        with suppress(Exception):
            await serve_task
        await reset_sse_shutdown_flag()

    return teardown, f"http://127.0.0.1:{port}/mcp"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_server_tools_render_into_skill_and_tool_docs() -> None:
    teardown, url = await _start_live_server()
    manager = MCPConnectionManager()
    try:
        cfg = MCPConfig(name="livesrv", type="streamable_http", url=url)
        conn = await manager.get_connection([cfg])
        assert conn is not None
        tools = conn.tools_by_server.get("livesrv")
        assert tools is not None and len(tools) == 4

        # Real wire call proves the transport is live (no mocks on this path).
        echo_out = await conn.call("livesrv", "echo", {"text": "hello"})
        assert "echo:hello" in str(echo_out)

        # --- Build SkillMetadata from the real tools ---
        generator = MCPSkillGenerator()
        skill_meta = generator._create_skill_metadata("livesrv", tools, user_description="live skill probe")
        assert skill_meta.is_mcp_skill is True
        assert skill_meta.mcp is not None
        assert len(skill_meta.mcp.tools) == 4

        # --- Level 2 SKILL.md: the calling contract is rendered unconditionally ---
        content = generator.generate_skill_content(skill_meta)
        assert SKILL_USAGE_TEMPLATE.format(skill_name=skill_meta.name) in content

        # --- Level 3 doc via MCPFileSystemStrategy: doc template owns the call contract ---
        skill_name = skill_meta.name
        strategy = MCPFileSystemStrategy([skill_meta])
        echo_doc = "\n".join(await strategy.read_file(f"/mcp/{skill_name}/echo.md"))
        assert "MCP Function Call Rules" not in echo_doc
        assert f"from skills.{skill_name} import echo" in echo_doc
        assert 'result = await echo(text="hello")' in echo_doc

        # A tool whose required parameters carry no example gets no placeholder call.
        add_doc = "\n".join(await strategy.read_file(f"/mcp/{skill_name}/add.md"))
        assert "## Parameters" in add_doc
        assert "## Import & Call Example" not in add_doc
    finally:
        # Release the pooled sessions before the server stops, or they reconnect to a dead port.
        await manager.close_all()
        await teardown()
