"""Public HTTP paths that bypass single-tenant auth middleware."""

from __future__ import annotations

# Open to every method: static webui entrypoints, the browser-login handshake and routes that carry their own
# credential (artifact-share token).
PUBLIC_PATH_PREFIXES: tuple[str, ...] = (
    "/api/v1/public/artifact-share",
    "/api/v1/webui/welcome",
    "/webui/auth/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/metrics",
)

# Open to read-only methods: the liveness and readiness probes that load balancers, the control plane and the desktop
# shell poll before any session exists. Everything else under /api/v1/health (diagnostics, metrics, resource and
# browser state, operator actions) goes through normal admission, and the host allowlist applies to it as well.
PUBLIC_READ_ONLY_EXACT_PATHS: frozenset[str] = frozenset(
    {
        "/api/v1/health",
        "/api/v1/health/liveness",
        "/api/v1/health/ready",
    }
)

READ_ONLY_METHODS: frozenset[str] = frozenset({"GET", "HEAD"})

# Exact paths (no trailing slash variants).
PUBLIC_EXACT_PATHS: frozenset[str] = frozenset(
    {
        "/",
        "/favicon.ico",
        "/health",
    }
)


def is_public_path(path: str, method: str) -> bool:
    """Return True when auth middleware should not require credentials for this request."""
    if path in PUBLIC_EXACT_PATHS or path.startswith(PUBLIC_PATH_PREFIXES):
        return True
    return method.upper() in READ_ONLY_METHODS and path in PUBLIC_READ_ONLY_EXACT_PATHS


__all__ = [
    "PUBLIC_EXACT_PATHS",
    "PUBLIC_PATH_PREFIXES",
    "PUBLIC_READ_ONLY_EXACT_PATHS",
    "READ_ONLY_METHODS",
    "is_public_path",
]
