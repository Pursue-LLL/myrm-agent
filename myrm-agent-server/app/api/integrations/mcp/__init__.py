"""MCP server inspection, registry and probe endpoints of the integrations API.

[INPUT]
- app.api.integrations.mcp.inspection::router (POS: options / scan / verify / resource routes, with the registry and probe routes mounted on it)

[OUTPUT]
- router: the MCP router the integrations router mounts under /mcp

[POS]
Package facade of the integrations MCP API: exposes the one router that the integrations router mounts under /mcp.
"""

from app.api.integrations.mcp.inspection import router

__all__ = ["router"]
