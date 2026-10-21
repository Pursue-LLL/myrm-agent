#!/usr/bin/env python3
"""Minimal stdio MCP server for Chrome E2E MCP settings add/save verify."""

from mcp.server import MCPServer

server = MCPServer(name="e2e-minimal", version="1.0.0")


def ping() -> str:
    """E2E noop tool for MCP verify."""
    return "pong"


server.add_tool(ping, name="ping", description="E2E noop tool for MCP verify")


if __name__ == "__main__":
    server.run(transport="stdio")
