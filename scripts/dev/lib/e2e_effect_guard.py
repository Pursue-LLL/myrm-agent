"""Runtime Effect Guard for formal Chrome E2E HTTP mutations (P0-C)."""

from __future__ import annotations

import os
from urllib.parse import urlparse

_GLOBAL_MUTATION_PREFIXES: tuple[str, ...] = (
    "/api/v1/config/",
    "/api/v1/features/",
    "/api/v1/admin/",
)


def current_access_scope() -> str:
    return os.environ.get("MYRM_E2E_ACCESS_SCOPE", "READ").strip().upper()


def _normalized_path(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or url
    if "/api/v1/" in path:
        path = path[path.index("/api/v1/") :]
    return path


def is_global_mutation_path(path: str) -> bool:
    normalized = path if path.startswith("/") else f"/{path}"
    return any(normalized.startswith(prefix) for prefix in _GLOBAL_MUTATION_PREFIXES)


def assert_http_effect_allowed(*, method: str, url: str) -> None:
    """Fail closed when READ/NAMESPACE_WRITE scope exceeds manifest."""
    scope = current_access_scope()
    verb = method.strip().upper()
    if verb in {"GET", "HEAD", "OPTIONS"}:
        return
    path = _normalized_path(url)
    if scope == "READ" and is_global_mutation_path(path):
        raise RuntimeError(f"E2E_EFFECT_GUARD: access_scope=READ forbids {verb} {path}")
    if scope == "NAMESPACE_WRITE" and is_global_mutation_path(path):
        namespace = os.environ.get("MYRM_E2E_NAMESPACE", "").strip()
        if namespace and namespace not in path:
            raise RuntimeError(
                f"E2E_EFFECT_GUARD: NAMESPACE_WRITE forbids global {verb} {path}"
            )


def guarded_httpx_request(
    client: object,
    method: str,
    url: str,
    **kwargs: object,
) -> object:
    """Effect-guarded httpx.Client.request wrapper for formal chrome_e2e."""
    assert_http_effect_allowed(method=method, url=url)
    request = getattr(client, "request")
    return request(method, url, **kwargs)
