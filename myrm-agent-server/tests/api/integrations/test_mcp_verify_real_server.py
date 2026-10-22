"""POST /mcp/verify against a real stdio MCP server process.

Pins the single-handshake guarantee end to end: one verification spawns the
server exactly once and still reports the server's real ``initialize``
instructions. The server logs one line per process start, so a regression that
re-introduces a second connection for the instructions shows up as a second line.
"""

from __future__ import annotations

import asyncio
import sys
import textwrap
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from myrm_agent_harness.toolkits.mcp import MCPAgent
from myrm_agent_harness.toolkits.mcp.config import MCPConfig

from app.api.integrations import mcp as mcp_mod
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")

_VERIFY_URL = "/api/v1/integrations/mcp/verify"
_SERVER_NAME = "probe"
_INSTRUCTIONS = "Call ping to check liveness."

_SERVER_SOURCE = """\
from pathlib import Path

from mcp.server import MCPServer

with Path({spawn_log!r}).open("a") as log:
    log.write("spawn\\n")

server = MCPServer(name="verify-probe", version="1.0.0", instructions={instructions!r})


def ping() -> str:
    return "pong"


server.add_tool(ping, name="ping", description="Liveness probe")

if __name__ == "__main__":
    server.run(transport="stdio")
"""


@dataclass(frozen=True)
class _StdioServer:
    script: Path
    spawn_log: Path

    @property
    def spawns(self) -> int:
        return len(self.spawn_log.read_text().splitlines()) if self.spawn_log.exists() else 0

    def verify_body(self) -> dict[str, object]:
        return {"name": _SERVER_NAME, "type": "stdio", "command": sys.executable, "args": [str(self.script)]}

    def agent_config(self) -> MCPConfig:
        return MCPConfig(name=_SERVER_NAME, type="stdio", command=sys.executable, args=[str(self.script)])


def _install_server(tmp_path: Path, instructions: str | None) -> _StdioServer:
    script = tmp_path / "verify_probe_server.py"
    spawn_log = tmp_path / "spawns.log"
    script.write_text(textwrap.dedent(_SERVER_SOURCE).format(spawn_log=str(spawn_log), instructions=instructions))
    return _StdioServer(script=script, spawn_log=spawn_log)


@dataclass(frozen=True)
class _Verified:
    response: Response
    server: _StdioServer
    agent: MCPAgent


@pytest.fixture
def client() -> Iterator[TestClient]:
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        yield TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def real_agent() -> Iterator[MCPAgent]:
    """A fresh real agent behind the endpoint, with a timeout generous enough for a cold interpreter start."""
    agent = MCPAgent()
    with (
        patch.object(mcp_mod, "_mcp_agent_instance", agent),
        patch.object(mcp_mod.settings.mcp, "verify_timeout", 60),
    ):
        yield agent


def _verify_real_server(client: TestClient, agent: MCPAgent, tmp_path: Path, instructions: str | None) -> _Verified:
    server = _install_server(tmp_path, instructions)
    return _Verified(client.post(_VERIFY_URL, json=server.verify_body()), server, agent)


def test_verify_spawns_the_server_once_and_returns_its_real_instructions(
    client: TestClient,
    real_agent: MCPAgent,
    tmp_path: Path,
) -> None:
    result = _verify_real_server(client, real_agent, tmp_path, _INSTRUCTIONS)

    assert result.response.status_code == 200, result.response.text
    data = result.response.json()["data"]
    assert data["instructions"] == _INSTRUCTIONS
    assert data["tools_count"] == 1
    assert data["tools"][0]["name"] == f"mcp__{_SERVER_NAME}__ping"
    assert result.server.spawns == 1, "verification must reuse the enumeration handshake instead of reconnecting"


def test_spawn_counter_detects_an_extra_handshake(client: TestClient, real_agent: MCPAgent, tmp_path: Path) -> None:
    """Positive control: the counter really observes every process start, so ``spawns == 1`` above is not vacuous."""
    result = _verify_real_server(client, real_agent, tmp_path, _INSTRUCTIONS)
    assert result.response.status_code == 200, result.response.text
    assert result.server.spawns == 1

    asyncio.run(real_agent.get_tools([result.server.agent_config()]))

    assert result.server.spawns == 2


def test_server_without_instructions_verifies_with_null_instructions_in_one_spawn(
    client: TestClient,
    real_agent: MCPAgent,
    tmp_path: Path,
) -> None:
    result = _verify_real_server(client, real_agent, tmp_path, None)

    assert result.response.status_code == 200, result.response.text
    assert result.response.json()["data"]["instructions"] is None
    assert result.server.spawns == 1
