"""MCP server inspection, registry and probe endpoints of the integrations API.

[INPUT]
- app.api.integrations.mcp.inspection::router (POS: options / scan / verify / resource routes, with the registry and probe routes mounted on it)

[OUTPUT]
- router: the MCP router the integrations router mounts under /mcp

[POS] app/api/integrations/mcp/__init__.py
"""

from app.api.integrations.mcp.inspection import router

__all__ = ["router"]
