"""Every API route needs a caller: a frontend path literal or a registered external consumer.

[POS]
tests/architecture/test_api_route_consumers.py

[INPUT]
- tests.support.public_api_app: full OpenAPI path + method table
- tests.support.frontend_api_paths: frontend path literals
- data/route_external_consumers.txt: routes called from outside the frontend, one `METHOD /path | evidence` per line
- data/route_consumer_baseline.txt: routes that predate this gate and still have no caller (shrink-only)

[OUTPUT]
- Fails when a route has neither a frontend caller, an external-consumer entry nor a baseline entry
- Fails when an entry goes stale (route gone, or it now has a caller) so both files can only shrink
- Fails when a route re-declares the API prefix it is already mounted under

A frontend caller is a path literal in a non-test frontend source (any call form: apiRequest, apiClient, fetch, ...)
whose segments equal the route's; a `${...}` literal segment only stands in for a route path parameter. The match is
per path, not per method, and a navigation literal for a page of the same name also counts, so the gate under-reports.
A route that nothing calls is a dead feature: delete it with its service code and tests, or register who calls it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.frontend_api_paths import FRONTEND_SRC, frontend_path_literals, segments
from tests.support.public_api_app import API_PREFIX, public_api_openapi

_SKIP_WITHOUT_FRONTEND = pytest.mark.skipif(not FRONTEND_SRC.is_dir(), reason="frontend sources are not part of this checkout")

_DATA = Path(__file__).resolve().parent / "data"
_VERBS = frozenset({"get", "post", "put", "delete", "patch"})
_WEBUI_MOUNT = "webui"

Operation = tuple[str, str]


def _read_entries(name: str) -> dict[Operation, str]:
    """`METHOD /path` or `METHOD /path | evidence` per line -> {(METHOD, path): evidence}."""
    entries: dict[Operation, str] = {}
    for line in (_DATA / name).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        operation, _, evidence = line.partition(" | ")
        method, path = operation.split(" ", 1)
        entries[(method, path)] = evidence.strip()
    return entries


def _operations() -> dict[Operation, tuple[str, ...]]:
    """(METHOD, client path) -> path segments with parameters collapsed to `{}`."""
    operations: dict[Operation, tuple[str, ...]] = {}
    for full_path, methods in public_api_openapi().paths.items():
        path = full_path.removeprefix(API_PREFIX)
        for method in methods:
            if method in _VERBS:
                operations[(method.upper(), path)] = segments(path)
    return operations


def _matches(route: tuple[str, ...], literals: dict[int, list[tuple[str, ...]]]) -> bool:
    return any(
        all(seen == expected or expected == "{}" for seen, expected in zip(literal, route, strict=True))
        for literal in literals.get(len(route), ())
    )


def has_frontend_caller(route: tuple[str, ...], literals: dict[int, list[tuple[str, ...]]]) -> bool:
    """`literals` is grouped by segment count; a literal segment equals the route's or fills a route parameter.

    The frontend reaches `/webui/**` through `getWebuiUrl()` / `webuiFetch()`, which add the mount prefix, so those
    routes are also matched without it.
    """
    mount_stripped = route[:1] + route[2:] if route[1:2] == (_WEBUI_MOUNT,) else None
    return _matches(route, literals) or (mount_stripped is not None and _matches(mount_stripped, literals))


def _group_by_length(literals: set[tuple[str, ...]]) -> dict[int, list[tuple[str, ...]]]:
    grouped: dict[int, list[tuple[str, ...]]] = {}
    for literal in literals:
        grouped.setdefault(len(literal), []).append(literal)
    return grouped


@pytest.fixture(scope="module")
def operations() -> dict[Operation, tuple[str, ...]]:
    return _operations()


@pytest.fixture(scope="module")
def uncovered(operations: dict[Operation, tuple[str, ...]]) -> set[Operation]:
    literals = _group_by_length({literal.segments for literal in frontend_path_literals()})
    assert literals, "no frontend path literals were discovered"
    return {operation for operation, route in operations.items() if not has_frontend_caller(route, literals)}


@_SKIP_WITHOUT_FRONTEND
def test_routes_have_callers(uncovered: set[Operation]) -> None:
    allowed = _read_entries("route_external_consumers.txt").keys() | _read_entries("route_consumer_baseline.txt").keys()
    orphaned = sorted(f"{method} {path}" for method, path in uncovered - allowed)
    assert not orphaned, (
        "routes without a frontend caller; delete them (with their service code and tests) or add the external "
        "consumer, with evidence, to tests/architecture/data/route_external_consumers.txt:\n" + "\n".join(orphaned)
    )


@_SKIP_WITHOUT_FRONTEND
def test_external_consumers_are_current(operations: dict[Operation, tuple[str, ...]], uncovered: set[Operation]) -> None:
    consumers = _read_entries("route_external_consumers.txt")
    unexplained = sorted(f"{method} {path}" for (method, path), evidence in consumers.items() if not evidence)
    assert not unexplained, f"every external consumer needs evidence (`METHOD /path | caller file:line`): {unexplained}"
    gone = sorted(f"{method} {path}" for method, path in consumers if (method, path) not in operations)
    assert not gone, f"route no longer exists, remove from route_external_consumers.txt: {gone}"
    covered = sorted(f"{method} {path}" for method, path in consumers if (method, path) not in uncovered)
    assert not covered, f"route now has a frontend caller, remove from route_external_consumers.txt: {covered}"


@_SKIP_WITHOUT_FRONTEND
def test_baseline_only_shrinks(operations: dict[Operation, tuple[str, ...]], uncovered: set[Operation]) -> None:
    baseline = _read_entries("route_consumer_baseline.txt").keys()
    registered = _read_entries("route_external_consumers.txt").keys()
    gone = sorted(f"{method} {path}" for method, path in baseline if (method, path) not in operations)
    assert not gone, f"route no longer exists, remove from route_consumer_baseline.txt: {gone}"
    settled = sorted(
        f"{method} {path}" for method, path in baseline if (method, path) not in uncovered or (method, path) in registered
    )
    assert not settled, f"route now has a caller or a registered consumer, remove from route_consumer_baseline.txt: {settled}"


def test_routes_do_not_repeat_the_api_prefix() -> None:
    doubled = sorted(f"{method} {path}" for method, path in _operations() if path.startswith(API_PREFIX + "/"))
    assert not doubled, f"routes already mounted under {API_PREFIX} must not declare the prefix again:\n" + "\n".join(doubled)


@pytest.mark.parametrize(
    ("literal", "route", "expected"),
    [
        (("", "memory", "head"), ("", "memory", "head"), True),
        (("", "memory", "abc"), ("", "memory", "{}"), True),
        (("", "memory", "{}"), ("", "memory", "{}"), True),
        (("", "memory", "{}"), ("", "memory", "head"), False),
        (("", "memory"), ("", "memory", "head"), False),
        (("", "auth", "status"), ("", "webui", "auth", "status"), True),
        (("", "auth", "status"), ("", "auth", "status", "extra"), False),
    ],
)
def test_has_frontend_caller_matches_whole_paths(literal: tuple[str, ...], route: tuple[str, ...], expected: bool) -> None:
    assert has_frontend_caller(route, _group_by_length({literal})) is expected
