#!/usr/bin/env python3
"""Minimal stdio MCP server for Chrome E2E MCP settings add/save verify."""

from mcp.server.fastmcp import FastMCP

server = FastMCP("e2e-minimal")


@server.tool()
def ping() -> str:
    """E2E noop tool for MCP verify."""
    return "pong"


if __name__ == "__main__":
    server.run(transport="stdio")
