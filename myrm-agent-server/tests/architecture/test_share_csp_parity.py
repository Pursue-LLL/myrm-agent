"""A shared page may load the CDNs the in-app preview allows, and every CDN the widget prompt tells the model to use.

A widget that renders in the preview is shared as the same document; when the share page's CDN list falls behind the
preview's, the chart or font it loads from a CDN is blocked and the shared copy renders blank.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.ai_agents.agent_middlewares.widget_capability_middleware import WIDGET_CAPABILITY_PROMPT
from app.core.security.share.share_csp import SHARE_CDN_SOURCES

_PREVIEW_TS = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "src" / "lib" / "widget-theme-bridge.ts"
_PREVIEW_LIST = re.compile(r"const CDN_ALLOWLIST = \[(.*?)\]\.join\(", re.DOTALL)
_PROMPT_LIST = re.compile(r"CDN allowlist:\s*(.+)")


def _preview_sources(ts_source: str) -> list[str]:
    block = _PREVIEW_LIST.search(ts_source)
    assert block is not None, "CDN_ALLOWLIST array is not defined in widget-theme-bridge.ts"
    return re.findall(r"'(https://[^']+)'", block.group(1))


def _prompt_origins(prompt: str) -> set[str]:
    line = _PROMPT_LIST.search(prompt)
    assert line is not None, "the widget prompt names no CDN allowlist"
    return {f"https://{host.strip()}" for host in line.group(1).split(",")}


@pytest.mark.skipif(not _PREVIEW_TS.exists(), reason="frontend sources are not part of this checkout")
def test_share_page_allows_exactly_the_cdns_the_preview_allows() -> None:
    preview = _preview_sources(_PREVIEW_TS.read_text(encoding="utf-8"))

    assert sorted(SHARE_CDN_SOURCES) == sorted(preview)


def test_share_page_allows_every_cdn_the_widget_prompt_names() -> None:
    assert _prompt_origins(WIDGET_CAPABILITY_PROMPT) <= set(SHARE_CDN_SOURCES)


def test_preview_list_reader_sees_every_entry_and_a_removed_one() -> None:
    ts = "const CDN_ALLOWLIST = [\n  'https://a.example',\n  'https://b.example',\n].join(' ');"

    assert _preview_sources(ts) == ["https://a.example", "https://b.example"]
    assert _preview_sources(ts.replace("  'https://b.example',\n", "")) == ["https://a.example"]


def test_prompt_list_reader_sees_every_host() -> None:
    prompt = "4. Background\n5. CDN allowlist: one.example, two.example\n6. CDN scripts"

    assert _prompt_origins(prompt) == {"https://one.example", "https://two.example"}
