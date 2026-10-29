"""MCP App UI resource proxy endpoint.

[INPUT]
- myrm_agent_harness.toolkits.mcp.connection_manager::MCPConnectionManager (POS: Pool of live MCP connections a resource is read through)
- app.config.settings::settings (POS: MCP verify timeout)
- app.core.utils.errors::external_service_error, timeout_error (POS: Error response helpers)
- app.core.utils.response_utils::success_response (POS: Standard JSON response builder)

[OUTPUT]
- router: FastAPI APIRouter with GET /resource
- read_mcp_resource

[POS]
Sub-router included by ``app.api.integrations.mcp.inspection``; lets the frontend fetch MCP App UI resources through an already-open connection.
"""

import asyncio
import logging

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.config.settings import settings
from app.core.utils.errors import external_service_error, timeout_error
from app.core.utils.response_utils import success_response

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/resource")
async def read_mcp_resource(
    uri: str = Query(..., description="MCP resource URI (e.g. ui://server/path)"),
    server: str = Query(..., description="MCP server name that owns the resource"),
) -> JSONResponse:
    """Proxy endpoint for frontend to fetch MCP App UI resources."""
    import base64

    from myrm_agent_harness.toolkits.mcp.connection_manager import MCPConnectionManager

    manager = MCPConnectionManager._instance
    if manager is None:
        raise external_service_error("MCP", "MCP connection pool not initialized")

    connections = manager._connections
    if not connections:
        raise external_service_error("MCP", "No active MCP connections")

    resource_bytes: bytes | None = None
    last_error: str = ""
    for conn in connections.values():
        try:
            resource_bytes = await asyncio.wait_for(
                conn.read_resource(server, uri),
                timeout=settings.mcp.verify_timeout,
            )
            break
        except RuntimeError as e:
            last_error = str(e)
            continue
        except asyncio.TimeoutError as exc:
            raise timeout_error(operation="MCP resource read") from exc
        except Exception as e:
            last_error = str(e)
            logger.warning("MCP resource read failed for server '%s': %s", server, e)
            continue

    if resource_bytes is None:
        raise external_service_error("MCP", f"Resource not found: {last_error}")

    content_b64 = base64.b64encode(resource_bytes).decode("ascii")
    mime_type = "text/html"
    if uri.endswith(".js"):
        mime_type = "application/javascript"
    elif uri.endswith(".css"):
        mime_type = "text/css"
    elif uri.endswith(".json"):
        mime_type = "application/json"

    return success_response(
        data={
            "content": content_b64,
            "mime_type": mime_type,
            "uri": uri,
            "server": server,
        }
    )
