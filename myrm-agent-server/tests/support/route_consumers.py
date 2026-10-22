"""Which API routes have a caller, shared by the architecture tests that need the answer.

[INPUT]
- tests.support.public_api_app: full OpenAPI path + method table
- tests.support.frontend_api_paths: frontend path literals
- tests/architecture/data/route_external_consumers.txt: routes called from outside the frontend, `METHOD /path | evidence`
- tests/architecture/data/route_consumer_baseline.txt: routes that predate the caller gate and still have no caller

[OUTPUT]
- Operation: (METHOD, client path without the API prefix)
- read_route_entries(name): {Operation: evidence} of one registry file
- api_operations(): every operation of the public API -> its path segments, parameters collapsed to `{}`
- has_frontend_caller() / group_by_length(): the match of a route against frontend path literals
- operations_without_frontend_caller(dynamic_matches_any): operations no frontend source calls
- operations_without_caller(dynamic_matches_any): those that no registry lists as called from outside either; empty without
  frontend sources

[POS]
架构测试共享的「路由有没有调用方」判定：「路由必须有调用方」与「用户文本入口必须过风险闸门」两个门禁对同一批路由取同一种解释。

A frontend caller is a path literal in a non-test frontend source (any call form: apiRequest, apiClient, fetch, ...)
whose segments equal the route's; a `${...}` literal segment only stands in for a route path parameter. The match is
per path, not per method, and a navigation literal for a page of the same name also counts, so it under-reports.

There are two questions. Whether a route is called asks for evidence, so a dynamic literal segment (``/agents/chats/${id}/${kind}``)
fills only a route parameter. Whether a route can be ruled out as called asks for the opposite: the same dynamic segment
may be any route segment, so with ``dynamic_matches_any`` it reaches every route of its shape.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from tests.support.frontend_api_paths import FRONTEND_SRC, frontend_path_literals, segments
from tests.support.public_api_app import API_PREFIX, API_VERBS, public_api_openapi

_DATA_DIR = Path(__file__).resolve().parents[1] / "architecture" / "data"
_EXTERNAL_CONSUMERS = "route_external_consumers.txt"
_WEBUI_MOUNT = "webui"

Operation = tuple[str, str]


def read_route_entries(name: str) -> dict[Operation, str]:
    """`METHOD /path` or `METHOD /path | evidence` per line -> {(METHOD, path): evidence}."""
    entries: dict[Operation, str] = {}
    for line in (_DATA_DIR / name).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        operation, _, evidence = line.partition(" | ")
        method, path = operation.split(" ", 1)
        entries[(method, path)] = evidence.strip()
    return entries


def api_operations() -> dict[Operation, tuple[str, ...]]:
    """(METHOD, client path) -> path segments with parameters collapsed to `{}`."""
    operations: dict[Operation, tuple[str, ...]] = {}
    for full_path, methods in public_api_openapi().paths.items():
        path = full_path.removeprefix(API_PREFIX)
        for method in methods:
            if method.upper() in API_VERBS:
                operations[(method.upper(), path)] = segments(path)
    return operations


def _matches(route: tuple[str, ...], literals: dict[int, list[tuple[str, ...]]], dynamic_matches_any: bool) -> bool:
    return any(
        all(
            seen == expected or expected == "{}" or (dynamic_matches_any and seen == "{}")
            for seen, expected in zip(literal, route, strict=True)
        )
        for literal in literals.get(len(route), ())
    )


def has_frontend_caller(
    route: tuple[str, ...], literals: dict[int, list[tuple[str, ...]]], dynamic_matches_any: bool = False
) -> bool:
    """`literals` is grouped by segment count; a literal segment equals the route's or fills a route parameter.
    With `dynamic_matches_any`, a dynamic literal segment (`${kind}`) also fills a literal route segment.

    The frontend reaches `/webui/**` through `getWebuiUrl()` / `webuiFetch()`, which add the mount prefix, so those
    routes are also matched without it.
    """
    mount_stripped = route[:1] + route[2:] if route[1:2] == (_WEBUI_MOUNT,) else None
    return _matches(route, literals, dynamic_matches_any) or (
        mount_stripped is not None and _matches(mount_stripped, literals, dynamic_matches_any)
    )


def group_by_length(literals: set[tuple[str, ...]]) -> dict[int, list[tuple[str, ...]]]:
    """Path literals by segment count, so a route is compared only with literals of its own length."""
    grouped: dict[int, list[tuple[str, ...]]] = {}
    for literal in literals:
        grouped.setdefault(len(literal), []).append(literal)
    return grouped


@cache
def operations_without_frontend_caller(dynamic_matches_any: bool = False) -> frozenset[Operation]:
    """Every operation whose path no non-test frontend source writes as a literal."""
    literals = group_by_length({literal.segments for literal in frontend_path_literals()})
    if not literals:
        raise AssertionError("no frontend path literals were discovered")
    return frozenset(
        operation
        for operation, route in api_operations().items()
        if not has_frontend_caller(route, literals, dynamic_matches_any)
    )


@cache
def operations_without_caller(dynamic_matches_any: bool = False) -> frozenset[Operation]:
    """Without the frontend sources the callers cannot be told, so no operation is called callerless."""
    if not FRONTEND_SRC.is_dir():
        return frozenset()
    return operations_without_frontend_caller(dynamic_matches_any) - read_route_entries(_EXTERNAL_CONSUMERS).keys()
