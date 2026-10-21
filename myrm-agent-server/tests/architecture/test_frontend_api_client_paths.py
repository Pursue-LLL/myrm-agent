"""Frontend API calls must target routes the server really serves.

[POS]
tests/architecture/test_frontend_api_client_paths.py

[INPUT]
- tests.support.public_api_app: full OpenAPI path + method table (api_router + webui router)
- tests.support.frontend_api_paths: frontend sources + path literals (apiRequest / apiClient call sites, `/api/v1/...` literals)

[OUTPUT]
- Fails when an apiRequest/apiClient call targets a missing route or method
- Fails when any frontend source spells out `/api/v1/...` (raw fetch, displayed webhook URL, ...) for a route that does not exist;
  a literal may stop at a base path of a route, and WebSocket endpoints are outside the OpenAPI table
- Fails when a `/api/<root>` literal leaves the server's `/api/v1` mount for a root nothing serves (`/api/webui/...`, `/api/memory/...`)
"""

from __future__ import annotations

import re

import pytest

from tests.support.frontend_api_paths import (
    FRONTEND_SRC,
    PATH_CHARS,
    frontend_path_literals,
    frontend_sources,
    normalize_path,
    segments,
)
from tests.support.public_api_app import API_PREFIX, public_api_openapi

_SKIP_WITHOUT_FRONTEND = pytest.mark.skipif(not FRONTEND_SRC.is_dir(), reason="frontend sources are not part of this checkout")

# Client calls whose server route does not exist yet; each entry must disappear once the route lands.
_KNOWN_MISSING_ROUTES: frozenset[tuple[str, str]] = frozenset()
# The same for `/api/v1/...` literals outside apiRequest/apiClient calls, as the literal's path below the API prefix.
_KNOWN_MISSING_LITERALS: frozenset[str] = frozenset()

# `/api/<root>` calls that leave the server's `/api/v1` mount are served by Next route handlers (src/app/api/*), by the
# control plane (reached through its own base URL) or by the channel ingress mounted at `/api/channels`.
_CONTROL_PLANE_ROOTS = frozenset(
    {"auth", "billing", "channels", "enterprise", "marketplace", "sandboxes", "security", "theme-marketplace"}
)
_API_VERSION_ROOT = API_PREFIX.rsplit("/", 1)[-1]

_CALL_RE = re.compile(
    r"(?:apiRequest|apiClient\.(?P<verb>get|post|put|delete|patch))"
    r"\s*(?:<[^>(]*>)?\(\s*(?P<quote>['\"`])(?P<path>/" + PATH_CHARS + r")"
    r"(?P<rest>[^;]{0,220})",
    re.DOTALL,
)
_METHOD_RE = re.compile(r"method:\s*'(?P<method>\w+)'")
_VERBS = frozenset({"get", "post", "put", "delete", "patch"})

RouteTable = list[tuple[tuple[str, ...], set[str]]]


def _client_calls() -> list[tuple[str, str, str]]:
    calls: list[tuple[str, str, str]] = []
    for name, text in frontend_sources():
        for match in _CALL_RE.finditer(text):
            if match.group("verb"):
                method = match.group("verb").upper()
            else:
                declared = _METHOD_RE.search(match.group("rest"))
                method = declared.group("method").upper() if declared else "GET"
            calls.append((name, method, normalize_path(match.group("path"))))
    return calls


def _route_table() -> RouteTable:
    table: RouteTable = []
    for path, operations in public_api_openapi().paths.items():
        client_path = path.removeprefix(API_PREFIX) if path.startswith(API_PREFIX) else path
        methods = {name.upper() for name in operations if name in _VERBS}
        table.append((segments(client_path), methods))
    return table


def _served(table: RouteTable, method: str, path: str) -> bool:
    """A literal client segment may stand in for a server path parameter and vice versa."""
    wanted = path.split("/")
    return any(
        method in methods
        and len(route) == len(wanted)
        and all(a == b or "{}" in (a, b) for a, b in zip(route, wanted, strict=True))
        for route, methods in table
    )


def _literal_targets_route(literal: tuple[str, ...], route: tuple[str, ...]) -> bool:
    """A literal may stop at a base path of the route (a prefix of its segments); `{}` on either side is a wildcard."""
    return len(literal) <= len(route) and all(a == b or "{}" in (a, b) for a, b in zip(literal, route, strict=False))


@pytest.fixture(scope="module")
def route_table() -> RouteTable:
    return _route_table()


@_SKIP_WITHOUT_FRONTEND
def test_frontend_clients_target_existing_routes(route_table: RouteTable) -> None:
    calls = _client_calls()
    assert calls, "no frontend client call sites were discovered"
    missing = sorted(
        {
            f"{method} {path} ({name})"
            for name, method, path in calls
            if not _served(route_table, method, path) and (method, path) not in _KNOWN_MISSING_ROUTES
        }
    )
    assert not missing, "frontend clients call routes the server does not serve:\n" + "\n".join(missing)


@_SKIP_WITHOUT_FRONTEND
def test_known_missing_routes_are_still_missing(route_table: RouteTable) -> None:
    resolved = sorted(f"{method} {path}" for method, path in _KNOWN_MISSING_ROUTES if _served(route_table, method, path))
    assert not resolved, f"route now exists, remove from _KNOWN_MISSING_ROUTES: {resolved}"


@_SKIP_WITHOUT_FRONTEND
def test_frontend_api_literals_target_existing_routes(route_table: RouteTable) -> None:
    routes = [route for route, _ in route_table]
    missing = sorted(
        {
            f"{'/'.join(literal.segments)} ({literal.source})"
            for literal in frontend_path_literals()
            if literal.prefixed
            and literal.segments[1] != "ws"
            and "/".join(literal.segments) not in _KNOWN_MISSING_LITERALS
            and not any(_literal_targets_route(literal.segments, route) for route in routes)
        }
    )
    assert not missing, f"frontend sources spell out {API_PREFIX} paths the server does not serve:\n" + "\n".join(missing)


@_SKIP_WITHOUT_FRONTEND
def test_known_missing_literals_are_still_missing(route_table: RouteTable) -> None:
    routes = [route for route, _ in route_table]
    resolved = sorted(
        path for path in _KNOWN_MISSING_LITERALS if any(_literal_targets_route(tuple(path.split("/")), route) for route in routes)
    )
    assert not resolved, f"route now exists, remove from _KNOWN_MISSING_LITERALS: {resolved}"


@pytest.mark.parametrize(
    ("literal", "route", "expected"),
    [
        (("", "cron", "trigger", "webhook", "{}"), ("", "cron", "trigger", "webhook", "{}"), True),
        (("", "cron", "triggers", "webhook", "{}"), ("", "cron", "trigger", "webhook", "{}"), False),
        (("", "evolution"), ("", "evolution", "{}", "rollback"), True),
        (("", "evolution", "{}", "rollback"), ("", "evolution", "pending", "rollback"), True),
        (("", "evolution", "history", "{}", "rollback"), ("", "evolution", "{}", "rollback"), False),
    ],
)
def test_literal_targets_route_semantics(literal: tuple[str, ...], route: tuple[str, ...], expected: bool) -> None:
    assert _literal_targets_route(literal, route) is expected


@_SKIP_WITHOUT_FRONTEND
def test_frontend_api_roots_are_served() -> None:
    next_handlers = {entry.name for entry in (FRONTEND_SRC / "app" / "api").iterdir() if entry.is_dir()}
    served = next_handlers | _CONTROL_PLANE_ROOTS | {_API_VERSION_ROOT}
    unknown = sorted(
        {
            f"/api/{root} ({literal.source})"
            for literal in frontend_path_literals()
            if not literal.prefixed and literal.segments[1:2] == ("api",) and len(literal.segments) > 2
            if (root := literal.segments[2].removesuffix("{}")) not in served
        }
    )
    assert not unknown, (
        "frontend sources call `/api/<root>` where no route handler, control plane or ingress serves it:\n" + "\n".join(unknown)
    )
