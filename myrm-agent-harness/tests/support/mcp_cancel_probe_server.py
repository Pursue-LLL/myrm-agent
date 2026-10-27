"""A real MCP server whose slow tool reports when it starts and when the server cancels it.

[INPUT]
- mcp.server.mcpserver::MCPServer (POS: real MCP protocol server; ``notifications/cancelled`` cancels the handler task)

[OUTPUT]
- build_cancel_probe_server: MCPServer with ``slow`` (long sleep) and ``fast`` tools; ``slow`` writes ``started`` on entry
  and ``cancelled`` when the server cancels it, both into the given directory
- STARTED / CANCELLED: the marker file names

[POS]
Harness pytest-only helper for caller-cancellation tests over real transports. Runnable as a stdio server
(``python mcp_cancel_probe_server.py <marks_dir>``) and importable to be served over HTTP, so both transports run the
same tool code. Self-contained (stdlib + ``mcp`` only) because the stdio child does not see the ``tests`` package.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer

STARTED = "started"
CANCELLED = "cancelled"


def build_cancel_probe_server(marks_dir: Path) -> MCPServer:
    server = MCPServer("cancel-probe")

    @server.tool()
    async def slow(seconds: float) -> str:
        (marks_dir / STARTED).write_text("1")
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            (marks_dir / CANCELLED).write_text("1")
            raise
        return "slow-done"

    @server.tool()
    async def fast() -> str:
        return "fast-done"

    return server


if __name__ == "__main__":
    build_cancel_probe_server(Path(sys.argv[1])).run(transport="stdio")
