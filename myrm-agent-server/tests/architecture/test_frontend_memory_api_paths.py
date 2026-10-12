"""Frontend memory service clients must call routes the memory router really serves.

[POS]
tests/architecture/test_frontend_memory_api_paths.py

[INPUT]
- tests.support.minimal_app: memory preset app (OpenAPI path + method table)
- myrm-agent-frontend/src/services/memory/*.ts: apiRequest / apiClient call sites

[OUTPUT]
- Fails when a client reintroduces the double `/api` prefix or targets a missing route or method.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.support.minimal_app import build_minimal_app

_SERVICES_DIR = (
    Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "src" / "services" / "memory"
)
_API_PREFIX = "/api/v1"
_SKIP_WITHOUT_FRONTEND = pytest.mark.skipif(
    not _SERVICES_DIR.is_dir(), reason="frontend sources are not part of this checkout"
)

# Client calls whose server route does not exist yet; each entry must disappear once the route lands.
_KNOWN_MISSING_ROUTES = frozenset(
    {
        ("GET", "/memory/retrieval/quadruple/stats"),
        ("GET", "/memory/cubes/records/{}"),
    }
)

# Template expressions holding a query string rather than a path segment.
_QUERY_EXPRESSIONS = frozenset({"qs", "qStr", "params", "query", "queryStr", "queryString"})

_PATH_CHARS = r"(?:\$\{[^}`]*\}|[^'\"`?\s$])*"
_CALL_RE = re.compile(
    r"(?:apiRequest|apiClient\.(?P<verb>get|post|put|delete|patch))"
    r"\s*(?:<[^>(]*>)?\(\s*(?P<quote>['\"`])(?P<path>/memory/" + _PATH_CHARS + r")"
    r"(?P<rest>[^;]{0,220})",
    re.DOTALL,
)
_METHOD_RE = re.compile(r"method:\s*'(?P<method>\w+)'")
_TEMPLATE_RE = re.compile(r"\$\{(?P<expr>[^}`]*)\}")
_PATH_CONST_RE = re.compile(r"const\s+(?P<name>\w+)\s*=\s*'(?P<value>/memory/[^'\s]*)'")


def _normalize(raw_path: str) -> str:
    """Collapse path parameters to `{}` and drop query-string templates."""
    without_query = _TEMPLATE_RE.sub(
        lambda m: "" if m.group("expr").strip() in _QUERY_EXPRESSIONS else m.group(0), raw_path
    )
    return _TEMPLATE_RE.sub("{}", without_query).rstrip("/")


def _normalize_server(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{}", path).rstrip("/")


def _source_with_path_constants(source: Path) -> str:
    text = source.read_text(encoding="utf-8")
    for constant in _PATH_CONST_RE.finditer(text):
        text = text.replace("${" + constant.group("name") + "}", constant.group("value"))
    return text


def _client_calls() -> list[tuple[str, str, str]]:
    calls: list[tuple[str, str, str]] = []
    for source in sorted(_SERVICES_DIR.glob("*.ts")):
        for match in _CALL_RE.finditer(_source_with_path_constants(source)):
            if match.group("verb"):
                method = match.group("verb").upper()
            else:
                declared = _METHOD_RE.search(match.group("rest"))
                method = declared.group("method").upper() if declared else "GET"
            calls.append((source.name, method, _normalize(match.group("path"))))
    return calls


@pytest.fixture(scope="module")
def server_routes() -> dict[str, set[str]]:
    table: dict[str, set[str]] = {}
    for path, operations in build_minimal_app(preset="memory").openapi()["paths"].items():
        if not path.startswith(_API_PREFIX):
            continue
        methods = {name.upper() for name in operations if name in {"get", "post", "put", "delete", "patch"}}
        table.setdefault(_normalize_server(path.removeprefix(_API_PREFIX)), set()).update(methods)
    return table


@_SKIP_WITHOUT_FRONTEND
def test_memory_clients_never_double_the_api_prefix() -> None:
    doubled = re.compile(r"['\"`/]api/(?:v1/)?memory")
    offenders = sorted(
        source.name
        for source in _SERVICES_DIR.glob("*.ts")
        if any(
            doubled.search(line) and "fetch(" not in line
            for line in source.read_text(encoding="utf-8").splitlines()
        )
    )
    assert not offenders, f"apiRequest already prepends {_API_PREFIX}; drop it in: {offenders}"


@_SKIP_WITHOUT_FRONTEND
def test_memory_clients_target_existing_routes(server_routes: dict[str, set[str]]) -> None:
    calls = _client_calls()
    assert calls, "no memory client call sites were discovered"
    missing = sorted(
        {
            f"{method} {path} ({name})"
            for name, method, path in calls
            if method not in server_routes.get(path, set())
            and (method, path) not in _KNOWN_MISSING_ROUTES
        }
    )
    assert not missing, "frontend memory clients call routes the server does not serve:\n" + "\n".join(missing)


@_SKIP_WITHOUT_FRONTEND
def test_known_missing_routes_are_still_missing(server_routes: dict[str, set[str]]) -> None:
    resolved = sorted(
        f"{method} {path}" for method, path in _KNOWN_MISSING_ROUTES if method in server_routes.get(path, set())
    )
    assert not resolved, f"route now exists, remove from _KNOWN_MISSING_ROUTES: {resolved}"
