"""Frontend apiRequest/apiClient calls must target routes the server really serves.

[POS]
tests/architecture/test_frontend_api_client_paths.py

[INPUT]
- tests.support.public_api_app: full OpenAPI path + method table (api_router + webui router)
- tests.support.frontend_api_paths: frontend sources + path normalization (apiRequest / apiClient call sites with literal paths)

[OUTPUT]
- Fails when a client reintroduces the double `/api` prefix or targets a missing route or method.
"""

from __future__ import annotations

import re

import pytest

from tests.support.frontend_api_paths import FRONTEND_SRC, PATH_CHARS, frontend_sources, normalize_path
from tests.support.public_api_app import API_PREFIX, public_api_openapi

_SKIP_WITHOUT_FRONTEND = pytest.mark.skipif(not FRONTEND_SRC.is_dir(), reason="frontend sources are not part of this checkout")

# Client calls whose server route does not exist yet; each entry must disappear once the route lands.
_KNOWN_MISSING_ROUTES: frozenset[tuple[str, str]] = frozenset()

_CALL_RE = re.compile(
    r"(?:apiRequest|apiClient\.(?P<verb>get|post|put|delete|patch))"
    r"\s*(?:<[^>(]*>)?\(\s*(?P<quote>['\"`])(?P<path>/" + PATH_CHARS + r")"
    r"(?P<rest>[^;]{0,220})",
    re.DOTALL,
)
_METHOD_RE = re.compile(r"method:\s*'(?P<method>\w+)'")
_VERBS = frozenset({"get", "post", "put", "delete", "patch"})


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


def _route_table() -> list[tuple[list[str], set[str]]]:
    table: list[tuple[list[str], set[str]]] = []
    for path, operations in public_api_openapi().paths.items():
        client_path = path.removeprefix(API_PREFIX) if path.startswith(API_PREFIX) else path
        methods = {name.upper() for name in operations if name in _VERBS}
        table.append((re.sub(r"\{[^}]*\}", "{}", client_path).rstrip("/").split("/"), methods))
    return table


def _served(table: list[tuple[list[str], set[str]]], method: str, path: str) -> bool:
    """A literal client segment may stand in for a server path parameter and vice versa."""
    segments = path.split("/")
    return any(
        method in methods
        and len(route) == len(segments)
        and all(a == b or "{}" in (a, b) for a, b in zip(route, segments, strict=True))
        for route, methods in table
    )


@pytest.fixture(scope="module")
def route_table() -> list[tuple[list[str], set[str]]]:
    return _route_table()


@_SKIP_WITHOUT_FRONTEND
def test_frontend_clients_target_existing_routes(route_table: list[tuple[list[str], set[str]]]) -> None:
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
def test_known_missing_routes_are_still_missing(route_table: list[tuple[list[str], set[str]]]) -> None:
    resolved = sorted(f"{method} {path}" for method, path in _KNOWN_MISSING_ROUTES if _served(route_table, method, path))
    assert not resolved, f"route now exists, remove from _KNOWN_MISSING_ROUTES: {resolved}"
