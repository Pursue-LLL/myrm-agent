"""Every `/memory/**` route needs a caller: a frontend path literal or a registered external consumer.

[POS]
tests/architecture/test_memory_route_callers.py

[INPUT]
- tests.support.public_api_app: full OpenAPI path + method table
- tests.support.frontend_api_paths: frontend sources + path normalization

[OUTPUT]
- Fails when a memory route has neither a frontend caller nor an `_EXTERNAL_CONSUMERS` entry, or when an entry goes stale.

A frontend caller is a path literal in a non-test frontend source (any call form: apiRequest, apiClient, fetch, ...)
whose segments equal the route's; a literal `${...}` segment only stands in for a route path parameter. The match is
per path, not per method.
"""

from __future__ import annotations

import re

import pytest

from tests.support.frontend_api_paths import FRONTEND_SRC, PATH_CHARS, frontend_sources, normalize_path
from tests.support.public_api_app import API_PREFIX, public_api_openapi

pytestmark = pytest.mark.skipif(not FRONTEND_SRC.is_dir(), reason="frontend sources are not part of this checkout")

_MEMORY_ROOT = "/memory"
_VERBS = frozenset({"get", "post", "put", "delete", "patch"})
_LITERAL_RE = re.compile(
    r"['\"`](?:" + re.escape(API_PREFIX) + r")?(?P<path>" + _MEMORY_ROOT + r"(?:/" + PATH_CHARS + r")?)(?![\w-])"
)

# Routes without a frontend caller; each one needs a consumer outside the frontend, or an owner decision on record.
_EXTERNAL_CONSUMERS: dict[tuple[str, str], str] = {
    (
        "GET",
        "/memory/head",
    ): "Polling probe for external clients and plugins (documented in getting-started/competitor-comparison)",
    ("GET", "/memory/command-center/plane-summary"): (
        "Polled by the control plane fleet health monitor (myrm-control-plane telemetry/fleet_health_monitor.py)"
    ),
    ("POST", "/memory/{memory_id}/correct"): (
        "Correction-chain verb of the memory REST resource; the UI corrects through command-center actions"
    ),
    ("GET", "/memory/retrieval/quadruple/items"): (
        "Quadruple retrieval index list API shipped with roadmap item 127 without a UI caller; owner to wire or remove"
    ),
    ("POST", "/memory/retrieval/quadruple/items"): (
        "Quadruple retrieval index ingest API shipped with roadmap item 127 without a UI caller; owner to wire or remove"
    ),
}


def _segments(path: str) -> tuple[str, ...]:
    return tuple(re.sub(r"\{[^}]*\}", "{}", path).rstrip("/").split("/"))


def _frontend_literals() -> set[tuple[str, ...]]:
    return {
        _segments(normalize_path(match.group("path"))) for _, text in frontend_sources() for match in _LITERAL_RE.finditer(text)
    }


def _memory_operations() -> dict[tuple[str, str], tuple[str, ...]]:
    """(METHOD, OpenAPI path) -> path segments with parameters collapsed to `{}`."""
    operations: dict[tuple[str, str], tuple[str, ...]] = {}
    for full_path, methods in public_api_openapi().paths.items():
        path = full_path.removeprefix(API_PREFIX)
        if path != _MEMORY_ROOT and not path.startswith(_MEMORY_ROOT + "/"):
            continue
        for method in methods:
            if method in _VERBS:
                operations[(method.upper(), path)] = _segments(path)
    return operations


def _has_frontend_caller(route: tuple[str, ...], literals: set[tuple[str, ...]]) -> bool:
    return any(
        len(literal) == len(route)
        and all(seen == expected or expected == "{}" for seen, expected in zip(literal, route, strict=True))
        for literal in literals
    )


@pytest.fixture(scope="module")
def uncovered_operations() -> set[tuple[str, str]]:
    literals = _frontend_literals()
    assert literals, "no frontend memory path literals were discovered"
    return {operation for operation, route in _memory_operations().items() if not _has_frontend_caller(route, literals)}


def test_memory_routes_have_callers(uncovered_operations: set[tuple[str, str]]) -> None:
    orphaned = sorted(f"{method} {path}" for method, path in uncovered_operations - _EXTERNAL_CONSUMERS.keys())
    assert not orphaned, (
        "memory routes without a frontend caller; delete them (with their service code and tests) or register the "
        "external consumer in _EXTERNAL_CONSUMERS:\n" + "\n".join(orphaned)
    )


def test_external_consumers_are_current(uncovered_operations: set[tuple[str, str]]) -> None:
    operations = _memory_operations()
    gone = sorted(f"{method} {path}" for method, path in _EXTERNAL_CONSUMERS if (method, path) not in operations)
    assert not gone, f"route no longer exists, remove from _EXTERNAL_CONSUMERS: {gone}"
    covered = sorted(f"{method} {path}" for method, path in _EXTERNAL_CONSUMERS if (method, path) not in uncovered_operations)
    assert not covered, f"route now has a frontend caller, remove from _EXTERNAL_CONSUMERS: {covered}"
