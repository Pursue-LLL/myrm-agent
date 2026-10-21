"""Every API route needs a caller: a frontend path literal or a registered external consumer.

[POS]
tests/architecture/test_api_route_consumers.py

[INPUT]
- tests.support.route_consumers: the route table, the frontend match and the registry files
- data/route_external_consumers.txt: routes called from outside the frontend, one `METHOD /path | evidence` per line
- data/route_consumer_baseline.txt: routes that predate this gate and still have no caller (shrink-only)

[OUTPUT]
- Fails when a route has neither a frontend caller, an external-consumer entry nor a baseline entry
- Fails when an entry goes stale (route gone, or it now has a caller) so both files can only shrink
- Fails when a route re-declares the API prefix it is already mounted under

What counts as a frontend caller, and why the gate under-reports, is described in tests/support/route_consumers.py.
A route that nothing calls is a dead feature: delete it with its service code and tests, or register who calls it.
"""

from __future__ import annotations

import pytest

from tests.support.frontend_api_paths import FRONTEND_SRC
from tests.support.public_api_app import API_PREFIX
from tests.support.route_consumers import (
    Operation,
    api_operations,
    group_by_length,
    has_frontend_caller,
    operations_without_frontend_caller,
    read_route_entries,
)

_SKIP_WITHOUT_FRONTEND = pytest.mark.skipif(not FRONTEND_SRC.is_dir(), reason="frontend sources are not part of this checkout")


@pytest.fixture(scope="module")
def operations() -> dict[Operation, tuple[str, ...]]:
    return api_operations()


@pytest.fixture(scope="module")
def uncovered() -> frozenset[Operation]:
    return operations_without_frontend_caller()


@_SKIP_WITHOUT_FRONTEND
def test_routes_have_callers(uncovered: frozenset[Operation]) -> None:
    allowed = read_route_entries("route_external_consumers.txt").keys() | read_route_entries("route_consumer_baseline.txt").keys()
    orphaned = sorted(f"{method} {path}" for method, path in uncovered - allowed)
    assert not orphaned, (
        "routes without a frontend caller; delete them (with their service code and tests) or add the external "
        "consumer, with evidence, to tests/architecture/data/route_external_consumers.txt:\n" + "\n".join(orphaned)
    )


@_SKIP_WITHOUT_FRONTEND
def test_external_consumers_are_current(operations: dict[Operation, tuple[str, ...]], uncovered: frozenset[Operation]) -> None:
    consumers = read_route_entries("route_external_consumers.txt")
    unexplained = sorted(f"{method} {path}" for (method, path), evidence in consumers.items() if not evidence)
    assert not unexplained, f"every external consumer needs evidence (`METHOD /path | caller file:line`): {unexplained}"
    gone = sorted(f"{method} {path}" for method, path in consumers if (method, path) not in operations)
    assert not gone, f"route no longer exists, remove from route_external_consumers.txt: {gone}"
    covered = sorted(f"{method} {path}" for method, path in consumers if (method, path) not in uncovered)
    assert not covered, f"route now has a frontend caller, remove from route_external_consumers.txt: {covered}"


@_SKIP_WITHOUT_FRONTEND
def test_baseline_only_shrinks(operations: dict[Operation, tuple[str, ...]], uncovered: frozenset[Operation]) -> None:
    baseline = read_route_entries("route_consumer_baseline.txt").keys()
    registered = read_route_entries("route_external_consumers.txt").keys()
    gone = sorted(f"{method} {path}" for method, path in baseline if (method, path) not in operations)
    assert not gone, f"route no longer exists, remove from route_consumer_baseline.txt: {gone}"
    settled = sorted(
        f"{method} {path}" for method, path in baseline if (method, path) not in uncovered or (method, path) in registered
    )
    assert not settled, f"route now has a caller or a registered consumer, remove from route_consumer_baseline.txt: {settled}"


def test_routes_do_not_repeat_the_api_prefix() -> None:
    doubled = sorted(f"{method} {path}" for method, path in api_operations() if path.startswith(API_PREFIX + "/"))
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
    assert has_frontend_caller(route, group_by_length({literal})) is expected
