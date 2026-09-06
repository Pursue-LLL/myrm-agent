"""Runtime Effect Guard for formal Chrome E2E HTTP mutations (P0-C)."""

from __future__ import annotations

import os
import posixpath
from urllib.parse import unquote, urlparse

# Global write prefixes audited across app/api (2026-08-09): config, features, admin,
# security (allowlist/estop/vault), org, voice, web_push, workspace. A mutation under
# any of these is a cross-session global write and must not run on the shared stack.
_GLOBAL_MUTATION_PREFIXES: tuple[str, ...] = (
    "/api/v1/config/",
    "/api/v1/features/",
    "/api/v1/admin/",
    "/api/v1/security/",
    "/api/v1/org/",
    "/api/v1/voice/",
    "/api/v1/web_push/",
    "/api/v1/workspace/",
    "/api/v1/statistics/",
)

# include_in_schema=False test-only fixture endpoint namespaces. Keep this
# allowlist explicit: a generic "/test/" substring would let an unrelated
# production mutation bypass the effect guard.
_TEST_FIXTURE_PREFIXES: tuple[str, ...] = (
    "/api/v1/approvals/test/",
    "/api/v1/background-tasks/test/",
    "/api/v1/chats/test/",
    "/api/v1/integrations/provider-oauth/test/",
    "/api/v1/memory/test/",
    "/api/v1/projects/test/",
    "/api/v1/security/allowlist/test/",
    "/api/v1/skills/drafts/test/",
    "/api/v1/skills/evolution/test/",
    "/api/v1/skills/test/",
    "/api/v1/tasks/test/",
)
_TEST_FIXTURE_EXACT_PATHS: frozenset[str] = frozenset(
    {"/api/v1/webui/desktop/approval/test-seed"}
)

# Formal chrome_e2e bootstrap helpers (prepare_e2e_ui_session) — idempotent UI gate, not tenant config.
_NAMESPACE_WRITE_BOOTSTRAP_PATHS: frozenset[str] = frozenset(
    {
        "/api/v1/config/onboarding/complete",
        "/api/v1/agents/test-media-config",
    }
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
    return normalized in _TEST_FIXTURE_EXACT_PATHS or any(
        normalized.startswith(prefix) for prefix in _TEST_FIXTURE_PREFIXES
    )


def is_global_mutation_path(path: str) -> bool:
    normalized = path if path.startswith("/") else f"/{path}"
    if is_test_fixture_path(normalized):
        return False
    return any(
        normalized == prefix.rstrip("/") or normalized.startswith(prefix)
        for prefix in _GLOBAL_MUTATION_PREFIXES
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
        if path in _NAMESPACE_WRITE_BOOTSTRAP_PATHS:
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
