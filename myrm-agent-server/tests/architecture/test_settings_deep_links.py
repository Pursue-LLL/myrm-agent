"""Every `/settings/<tab>` deep link the product emits must resolve to a real settings route.

[POS]
tests/architecture/test_settings_deep_links.py

[INPUT]
- myrm-agent-frontend/src/components/features/settings/settingsRoutes.ts: SETTINGS_TABS + SETTINGS_TAB_REDIRECTS (route SSOT)
- myrm-agent-frontend/src/**/*.ts(x), myrm-agent-server/app/**/*.py, myrm-agent-server/assets/**:
  `/settings/<tab>` literals in links, router pushes, push payloads, cron summaries and prebuilt skills

[OUTPUT]
- Fails when a literal targets an id that is neither a routable tab nor a redirect alias, which would
  land users on a 404 (or a silently wrong page) instead of the settings screen the text promises.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_MYRM_AGENT_ROOT = Path(__file__).resolve().parents[3]
_FRONTEND_SRC = _MYRM_AGENT_ROOT / "myrm-agent-frontend" / "src"
_ROUTES_FILE = _FRONTEND_SRC / "components" / "features" / "settings" / "settingsRoutes.ts"
_SERVER_APP = _MYRM_AGENT_ROOT / "myrm-agent-server" / "app"
_SERVER_ASSETS = _MYRM_AGENT_ROOT / "myrm-agent-server" / "assets"

_SKIP_WITHOUT_FRONTEND = pytest.mark.skipif(not _ROUTES_FILE.is_file(), reason="frontend sources are not part of this checkout")

_SCANNED_ROOTS: tuple[tuple[Path, frozenset[str]], ...] = (
    (_FRONTEND_SRC, frozenset({".ts", ".tsx"})),
    (_SERVER_APP, frozenset({".py"})),
    (_SERVER_ASSETS, frozenset({".md", ".json", ".yaml", ".yml"})),
)

# `/settings/<id>` not preceded by a path/word character, so `/api/v1/settings/...` never matches.
_DEEP_LINK_RE = re.compile(r"(?<![\w/.\-])/settings/(?P<tab>[A-Za-z0-9_-]+)")
# FastAPI router prefixes share the `/settings/` namespace but are API routes, not WebUI pages.
_API_PREFIX_MARKER = "prefix="
_TABS_BLOCK_RE = re.compile(r"SETTINGS_TABS\s*=\s*\[(?P<body>.*?)\]\s*as\s*const", re.DOTALL)
_REDIRECT_KEY_RE = re.compile(r"^\s{2}(?:'(?P<quoted>[^']+)'|(?P<bare>[A-Za-z]\w*)):\s*\{\s*parent:", re.MULTILINE)


def _is_test_source(path: Path) -> bool:
    return "__tests__" in path.parts or ".test." in path.name


def _route_ids() -> tuple[frozenset[str], frozenset[str]]:
    source = _ROUTES_FILE.read_text(encoding="utf-8")
    tabs_block = _TABS_BLOCK_RE.search(source)
    assert tabs_block is not None, "SETTINGS_TABS block not found in settingsRoutes.ts"
    tabs = frozenset(re.findall(r"'([^']+)'", tabs_block.group("body")))
    aliases = frozenset(match.group("quoted") or match.group("bare") for match in _REDIRECT_KEY_RE.finditer(source))
    return tabs, aliases


def _deep_link_literals() -> list[tuple[Path, int, str]]:
    found: list[tuple[Path, int, str]] = []
    for root, suffixes in _SCANNED_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix not in suffixes or not path.is_file() or _is_test_source(path):
                continue
            for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
                if _API_PREFIX_MARKER in line:
                    continue
                found.extend((path, line_no, match.group("tab")) for match in _DEEP_LINK_RE.finditer(line))
    return found


@_SKIP_WITHOUT_FRONTEND
@pytest.mark.architecture
def test_settings_route_ssot_parses() -> None:
    tabs, aliases = _route_ids()

    assert {"account", "wiki", "mcp", "credentials", "models", "extensionBridge", "workbench", "shares"} <= tabs
    assert {"defaultModel", "persona", "eval"} <= aliases
    assert aliases.isdisjoint({"wiki", "mcp", "credentials", "models"})


@_SKIP_WITHOUT_FRONTEND
@pytest.mark.architecture
def test_settings_deep_links_resolve_to_known_routes() -> None:
    tabs, aliases = _route_ids()
    known = tabs | aliases

    unknown = [
        f"{path.relative_to(_MYRM_AGENT_ROOT)}:{line_no}: /settings/{tab}"
        for path, line_no, tab in _deep_link_literals()
        if tab not in known
    ]

    assert not unknown, "deep links to non-existent settings routes:\n" + "\n".join(unknown)
