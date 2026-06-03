"""Public HTTP paths that bypass single-tenant auth middleware."""

from __future__ import annotations

# Prefix match — keep health, OpenAPI, and static webui entrypoints open.
PUBLIC_PATH_PREFIXES: tuple[str, ...] = (
    "/api/v1/health",
    "/api/v1/webui/welcome",
    "/webui/auth/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/metrics",
)

# Exact paths (no trailing slash variants).
PUBLIC_EXACT_PATHS: frozenset[str] = frozenset(
    {
        "/",
        "/favicon.ico",
    }
)


def is_public_path(path: str) -> bool:
    """Return True when auth middleware should not require credentials."""
    if path in PUBLIC_EXACT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)


__all__ = ["PUBLIC_EXACT_PATHS", "PUBLIC_PATH_PREFIXES", "is_public_path"]
