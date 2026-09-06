"""Runtime Effect Guard for formal Chrome E2E HTTP mutations (P0-C)."""

from __future__ import annotations

import os
import posixpath
from urllib.parse import unquote, urlparse

from e2e_core.effect_policy import (
    GLOBAL_MUTATION_PREFIXES,
    NAMESPACE_WRITE_BOOTSTRAP_PATHS,
    TEST_FIXTURE_EXACT_PATHS,
    TEST_FIXTURE_PREFIXES,
)


def current_access_scope() -> str:
    return os.environ.get("MYRM_E2E_ACCESS_SCOPE", "READ").strip().upper()


def _normalized_path(url: str) -> str:
    parsed = urlparse(url)
    path = unquote(parsed.path or url)
    if "/api/v1/" in path:
        path = path[path.index("/api/v1/") :]
    return posixpath.normpath(path)


def is_test_fixture_path(path: str) -> bool:
    normalized = path if path.startswith("/") else f"/{path}"
    return normalized in TEST_FIXTURE_EXACT_PATHS or any(
        normalized.startswith(prefix) for prefix in TEST_FIXTURE_PREFIXES
    )


def is_global_mutation_path(path: str) -> bool:
    normalized = path if path.startswith("/") else f"/{path}"
    if is_test_fixture_path(normalized):
        return False
    return any(
        normalized == prefix.rstrip("/") or normalized.startswith(prefix)
        for prefix in GLOBAL_MUTATION_PREFIXES
    )


def assert_http_effect_allowed(*, method: str, url: str) -> None:
    """Enforce the declared effect scope before any mutating HTTP request.

    Fixture endpoints are explicitly test-only and carry their own run
    namespace. Every other mutation must either be an explicitly approved
    bootstrap action or run in PRIVATE; a substring in a URL is never treated
    as proof of resource ownership.
    """
    scope = current_access_scope()
    verb = method.strip().upper()
    if verb in {"GET", "HEAD", "OPTIONS"}:
        return
    path = _normalized_path(url)
    if is_test_fixture_path(path):
        return
    if scope == "READ":
        raise RuntimeError(f"E2E_EFFECT_GUARD: access_scope=READ forbids {verb} {path}")
    if scope == "NAMESPACE_WRITE":
        namespace = os.environ.get("MYRM_E2E_NAMESPACE", "").strip()
        if not namespace:
            raise RuntimeError(
                "E2E_EFFECT_GUARD: NAMESPACE_WRITE requires MYRM_E2E_NAMESPACE"
            )
        if path in NAMESPACE_WRITE_BOOTSTRAP_PATHS:
            return
        if is_global_mutation_path(path):
            raise RuntimeError(
                f"E2E_EFFECT_GUARD: NAMESPACE_WRITE forbids global {verb} {path}"
            )
        return
    if scope == "GLOBAL_WRITE":
        mode = os.environ.get("MYRM_E2E_EXECUTION_MODE", "").strip().upper()
        if mode != "PRIVATE":
            raise RuntimeError(
                "E2E_EFFECT_GUARD: GLOBAL_WRITE requires PRIVATE execution"
            )
        return
    raise RuntimeError(f"E2E_EFFECT_GUARD: unknown access_scope={scope!r}")


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
