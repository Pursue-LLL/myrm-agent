"""Frontend apiRequest/apiClient calls must target routes the server really serves.

[POS]
tests/architecture/test_frontend_api_client_paths.py

[INPUT]
- app.api.router.api_router (+ webui router): full OpenAPI path + method table
- myrm-agent-frontend/src/**/*.ts(x): apiRequest / apiClient call sites with literal paths

[OUTPUT]
- Fails when a client reintroduces the double `/api` prefix or targets a missing route or method.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI

_FRONTEND_SRC = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "src"
_API_PREFIX = "/api/v1"
_WEBUI_PREFIX = "/webui"
_SKIP_WITHOUT_FRONTEND = pytest.mark.skipif(not _FRONTEND_SRC.is_dir(), reason="frontend sources are not part of this checkout")

# Client calls whose server route does not exist yet; each entry must disappear once the route lands.
_KNOWN_MISSING_ROUTES = frozenset(
    {
        ("GET", "/memory/retrieval/quadruple/stats"),
        ("GET", "/memory/cubes/records/{}"),
    }
)

# Template expressions holding a query string rather than a path segment.
_QUERY_EXPRESSIONS = frozenset({"q", "qs", "qStr", "params", "query", "queryStr", "queryString"})

_PATH_CHARS = r"(?:\$\{[^}`]*\}|[^'\"`?\s$])*"
_CALL_RE = re.compile(
    r"(?:apiRequest|apiClient\.(?P<verb>get|post|put|delete|patch))"
    r"\s*(?:<[^>(]*>)?\(\s*(?P<quote>['\"`])(?P<path>/" + _PATH_CHARS + r")"
    r"(?P<rest>[^;]{0,220})",
    re.DOTALL,
)
_METHOD_RE = re.compile(r"method:\s*'(?P<method>\w+)'")
_TEMPLATE_RE = re.compile(r"\$\{(?P<expr>[^}`]*)\}")
_PATH_CONST_RE = re.compile(r"const\s+(?P<name>\w+)\s*=\s*'(?P<value>/[^'\s]*)'")
_VERBS = frozenset({"get", "post", "put", "delete", "patch"})


def _normalize(raw_path: str) -> str:
    """Collapse path parameters to `{}` and drop query-string templates."""
    without_query = _TEMPLATE_RE.sub(lambda m: "" if m.group("expr").strip() in _QUERY_EXPRESSIONS else m.group(0), raw_path)
    return _TEMPLATE_RE.sub("{}", without_query).rstrip("/")


def _source_with_path_constants(text: str) -> str:
    for constant in _PATH_CONST_RE.finditer(text):
        text = text.replace("${" + constant.group("name") + "}", constant.group("value"))
    return text


def _client_calls() -> list[tuple[str, str, str]]:
    calls: list[tuple[str, str, str]] = []
    for source in sorted([*_FRONTEND_SRC.rglob("*.ts"), *_FRONTEND_SRC.rglob("*.tsx")]):
        if "__tests__" in source.parts or ".test." in source.name:
            continue
        text = _source_with_path_constants(source.read_text(encoding="utf-8"))
        for match in _CALL_RE.finditer(text):
            if match.group("verb"):
                method = match.group("verb").upper()
            else:
                declared = _METHOD_RE.search(match.group("rest"))
                method = declared.group("method").upper() if declared else "GET"
            calls.append((str(source.relative_to(_FRONTEND_SRC)), method, _normalize(match.group("path"))))
    return calls


def _route_table() -> list[tuple[list[str], set[str]]]:
    from app.api.internal.org_policy_sync.org_model_policy_sync import frontend_router as org_policy_router
    from app.api.router import api_router
    from app.api.webui.router import router as webui_router

    app = FastAPI()
    app.include_router(api_router, prefix=_API_PREFIX)
    app.include_router(org_policy_router, prefix=_API_PREFIX)
    app.include_router(webui_router)
    table: list[tuple[list[str], set[str]]] = []
    for path, operations in app.openapi()["paths"].items():
        client_path = path.removeprefix(_API_PREFIX) if path.startswith(_API_PREFIX) else path
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
