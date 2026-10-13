"""Frontend API path scanning shared by the API-surface architecture tests.

[INPUT]
- myrm-agent-frontend/src/**/*.ts(x): non-test sources; `const NAME = '/path'` constants are inlined

[OUTPUT]
- FRONTEND_SRC / PATH_CHARS: source root and the pattern of a literal API path
- frontend_sources(): (relative name, source text) pairs
- normalize_path(): `${...}` collapsed to `{}`, query-string templates dropped

[POS]
架构测试共享的前端源码扫描；「前端调用必须命中路由」与「路由必须有前端调用」两个方向共用同一套路径归一化。
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

FRONTEND_SRC = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "src"

# Template expressions holding a query string rather than a path segment.
_QUERY_EXPRESSIONS = frozenset({"q", "qs", "qStr", "params", "query", "queryStr", "queryString"})

PATH_CHARS = r"(?:\$\{[^}`]*\}|[^'\"`?\s$])*"
_TEMPLATE_RE = re.compile(r"\$\{(?P<expr>[^}`]*)\}")
_PATH_CONST_RE = re.compile(r"const\s+(?P<name>\w+)\s*=\s*'(?P<value>/[^'\s]*)'")


def normalize_path(raw_path: str) -> str:
    """Collapse path parameters to `{}` and drop query-string templates."""
    without_query = _TEMPLATE_RE.sub(lambda m: "" if m.group("expr").strip() in _QUERY_EXPRESSIONS else m.group(0), raw_path)
    return _TEMPLATE_RE.sub("{}", without_query).rstrip("/")


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
