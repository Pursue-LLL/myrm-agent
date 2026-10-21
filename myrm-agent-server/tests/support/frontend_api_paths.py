"""Frontend API path scanning shared by the API-surface architecture tests.

[INPUT]
- myrm-agent-frontend/src/**/*.ts(x): non-test sources; `const NAME = '/path'` constants are inlined

[OUTPUT]
- FRONTEND_SRC / PATH_CHARS: source root and the pattern of a literal API path
- frontend_sources(): (relative name, source text) pairs
- normalize_path() / segments(): `${...}` and `{param}` collapsed to `{}`, query-string templates dropped
- frontend_path_literals(): every path-shaped string literal as PathLiteral(source, segments, prefixed)

[POS]
架构测试共享的前端源码扫描；「前端调用必须命中路由」与「路由必须有前端调用」两个方向共用同一套路径归一化。
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path
from typing import NamedTuple

from tests.support.public_api_app import API_PREFIX

FRONTEND_SRC = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "src"

# Template expressions holding a query string rather than a path segment.
_QUERY_EXPRESSIONS = frozenset({"q", "qs", "qStr", "params", "query", "queryStr", "queryString"})

PATH_CHARS = r"(?:\$\{[^}`]*\}|[^'\"`?\s$])*"
_TEMPLATE_RE = re.compile(r"\$\{(?P<expr>[^}`]*)\}")
_PATH_CONST_RE = re.compile(r"const\s+(?P<name>\w+)\s*=\s*'(?P<value>/[^'\s]*)'")
_PARAM_RE = re.compile(r"\{[^}]*\}")
# `${API_BASE_URL}/x` and `${getBackendUrl()}/api/v1/x` templates lead with a base expression before the path.
_LITERAL_RE = re.compile(
    r"['\"`](?:\$\{[A-Za-z_][\w.]*(?:\(\))?\})?(?P<prefix>"
    + re.escape(API_PREFIX)
    + r")?(?P<path>/[A-Za-z][\w-]*(?:/"
    + PATH_CHARS
    + r")?)(?![\w-])"
)


class PathLiteral(NamedTuple):
    """A path-shaped string literal; `prefixed` marks one that spells out the API prefix itself."""

    source: str
    segments: tuple[str, ...]
    prefixed: bool


def normalize_path(raw_path: str) -> str:
    """Collapse path parameters to `{}` and drop query-string templates."""
    without_query = _TEMPLATE_RE.sub(lambda m: "" if m.group("expr").strip() in _QUERY_EXPRESSIONS else m.group(0), raw_path)
    return _TEMPLATE_RE.sub("{}", without_query).rstrip("/")


def segments(path: str) -> tuple[str, ...]:
    """Path segments with every path parameter (`{id}` of a route, `${id}` of a template) collapsed to `{}`."""
    return tuple(_PARAM_RE.sub("{}", path).rstrip("/").split("/"))


def _inline_path_constants(text: str) -> str:
    for constant in _PATH_CONST_RE.finditer(text):
        text = text.replace("${" + constant.group("name") + "}", constant.group("value"))
    return text


@cache
def frontend_sources() -> tuple[tuple[str, str], ...]:
    """Every non-test frontend source as (path relative to src, text with path constants inlined)."""
    sources: list[tuple[str, str]] = []
    for source in sorted([*FRONTEND_SRC.rglob("*.ts"), *FRONTEND_SRC.rglob("*.tsx")]):
        if "__tests__" in source.parts or ".test." in source.name:
            continue
        sources.append((str(source.relative_to(FRONTEND_SRC)), _inline_path_constants(source.read_text(encoding="utf-8"))))
    return tuple(sources)


@cache
def frontend_path_literals() -> tuple[PathLiteral, ...]:
    """Every path-shaped literal of the non-test sources, in any call form (apiRequest, apiClient, fetch, ...)."""
    return tuple(
        PathLiteral(name, segments(normalize_path(match.group("path"))), match.group("prefix") is not None)
        for name, text in frontend_sources()
        for match in _LITERAL_RE.finditer(text)
    )
