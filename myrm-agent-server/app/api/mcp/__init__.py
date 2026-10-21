"""MCP memory endpoint mount helpers.

[INPUT]
- .endpoint::setup_mcp_endpoint, shutdown_mcp_endpoint, _MCPTokenAuthMiddleware
- .origin_guard::OriginGuard, GuardVerdict, check_request_origin

[OUTPUT]
- setup_mcp_endpoint, shutdown_mcp_endpoint, OriginGuard, check_request_origin

[POS]
Package entry point for MCP memory endpoint mounting and origin guard verification.
"""

from app.api.mcp.endpoint import (
    _MCPTokenAuthMiddleware,
    setup_mcp_endpoint,
    shutdown_mcp_endpoint,
)
from app.api.mcp.origin_guard import (
    GuardVerdict,
    OriginGuard,
    _MCPOriginGuardMiddleware,
    check_request_origin,
    is_loopback_hostname,
    resolve_origin_guard,
)

__all__ = [
    "GuardVerdict",
    "OriginGuard",
    "_MCPOriginGuardMiddleware",
    "_MCPTokenAuthMiddleware",
    "check_request_origin",
    "is_loopback_hostname",
    "resolve_origin_guard",
    "setup_mcp_endpoint",
    "shutdown_mcp_endpoint",
]
