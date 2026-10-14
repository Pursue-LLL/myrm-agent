"""Public HTTP paths that bypass single-tenant auth middleware."""

from __future__ import annotations

# Open to every method: static webui entrypoints, the browser-login handshake and routes that carry their own
# credential (artifact-share token, A2A peer bearer token).
PUBLIC_PATH_PREFIXES: tuple[str, ...] = (
    "/api/v1/public/artifact-share",
    "/api/v1/webui/welcome",
    "/api/v1/a2a/agents/",
    "/webui/auth/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/metrics",
)

# Open to read-only methods: liveness and diagnostics probes. The same prefix also hosts mutating operator actions
# (database reset, purge, repair, probes) that must go through normal admission.
PUBLIC_READ_ONLY_PREFIXES: tuple[str, ...] = ("/api/v1/health",)

READ_ONLY_METHODS: frozenset[str] = frozenset({"GET", "HEAD"})

# Exact paths (no trailing slash variants).
PUBLIC_EXACT_PATHS: frozenset[str] = frozenset(
    {
        "/",
        "/.well-known/agent-card.json",
        "/api/v1/a2a/.well-known/agent-card.json",
        "/api/v1/a2a/rpc",
        "/favicon.ico",
        "/health",
    }
)


def is_public_path(path: str, method: str) -> bool:
    """Return True when auth middleware should not require credentials for this request."""
    if path in PUBLIC_EXACT_PATHS or path.startswith(PUBLIC_PATH_PREFIXES):
        return True
    return method.upper() in READ_ONLY_METHODS and path.startswith(PUBLIC_READ_ONLY_PREFIXES)


__all__ = [
    "PUBLIC_EXACT_PATHS",
    "PUBLIC_PATH_PREFIXES",
    "PUBLIC_READ_ONLY_PREFIXES",
    "READ_ONLY_METHODS",
    "is_public_path",
]
