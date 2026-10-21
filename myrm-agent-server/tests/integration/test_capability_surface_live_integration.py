"""Live integration: MCP runtime prepare + routing without mocks on harness path."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from myrm_agent_harness.agent._factory.mcp_routing import route_mcp_servers
from myrm_agent_harness.toolkits.mcp.config import MCPConfig
from myrm_agent_harness.toolkits.mcp.connection_manager import MCPConnectionManager


def _write_ping_server(script_path: Path) -> None:
    script_path.write_text(
        "\n".join(
            [
                "from mcp.server import MCPServer",
                "",
                'server = MCPServer("live-prepare-probe")',
                "",
                "@server.tool()",
                "def ping() -> str:",
                '    """Ping for live prepare + route integration."""',
                '    return "pong"',
                "",
                'if __name__ == "__main__":',
                '    server.run(transport="stdio")',
            ]
        ),
        encoding="utf-8",
    )


@pytest.fixture
def _reset_manager() -> object:
    MCPConnectionManager._instance = None
    yield
    MCPConnectionManager._instance = None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_prepare_then_route_real_stdio_mcp(
    tmp_path: Path,
    _reset_manager: object,
) -> None:
    """prepare_mcp_configs_for_runtime → route_mcp_servers on real stdio MCP (no routing mocks)."""
    from app.services.agent.mcp_runtime_prepare import prepare_mcp_configs_for_runtime

    script = tmp_path / "live_prepare_ping.py"
    _write_ping_server(script)

    raw_cfg = MCPConfig(
        name="live-prepare-probe",
        type="stdio",
        command=sys.executable,
        args=[str(script)],
        description="Live prepare + route integration probe",
        connect_timeout=45.0,
    )

    prepared = await prepare_mcp_configs_for_runtime(None, [raw_cfg])
    assert len(prepared) == 1
    assert prepared[0].name == "live-prepare-probe"

    manager = await MCPConnectionManager.get_instance()
    try:
        result = await route_mcp_servers(prepared)
        assert len(result.direct_tools) >= 1
        assert result.skills == []
    finally:
        await manager.stop()
