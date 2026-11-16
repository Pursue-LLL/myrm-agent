"""The language the wiki agent tools are described in: the text a locale selects, and the tools carrying it."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.toolkits.wiki import WikiStructure, create_wiki_tools
from myrm_agent_harness.toolkits.wiki.wiki_tool_descriptions import (
    WIKI_APPLY_DESCRIPTION_EN,
    WIKI_APPLY_DESCRIPTION_ZH,
    WIKI_INGEST_DESCRIPTION_EN,
    WIKI_INGEST_DESCRIPTION_ZH,
    WIKI_QUERY_DESCRIPTION_EN,
    WIKI_QUERY_DESCRIPTION_ZH,
)

# Tool name -> (English text, Chinese text)
_TEXTS = {
    "wiki_ingest_tool": (WIKI_INGEST_DESCRIPTION_EN, WIKI_INGEST_DESCRIPTION_ZH),
    "wiki_query_tool": (WIKI_QUERY_DESCRIPTION_EN, WIKI_QUERY_DESCRIPTION_ZH),
    "wiki_apply_tool": (WIKI_APPLY_DESCRIPTION_EN, WIKI_APPLY_DESCRIPTION_ZH),
}

_LOCALES = [
    pytest.param(None, False, id="no-locale"),
    pytest.param("en", False, id="en"),
    pytest.param("fr", False, id="language-without-a-translation"),
    pytest.param("zh-CN", True, id="zh-CN"),
    pytest.param("zh-TW", True, id="zh-TW"),
]


@pytest.mark.parametrize(("locale", "chinese"), _LOCALES)
@pytest.mark.parametrize("tool_name", sorted(_TEXTS))
def test_each_tool_is_described_in_the_language_of_its_locale(
    tool_name: str, locale: str | None, chinese: bool, wiki_structure: WikiStructure
) -> None:
    tools = create_wiki_tools(MagicMock(), MagicMock(), wiki_structure, locale=locale)

    english, chinese_text = _TEXTS[tool_name]
    # The tool framework trims the text's trailing newline.
    assert {tool.name: tool.description for tool in tools}[tool_name] == (chinese_text if chinese else english).strip()


def test_the_chinese_apply_text_protects_only_the_claims_in_the_frontmatter() -> None:
    # update_metadata edits the frontmatter's tags, aliases and sources, so the frontmatter as a whole is not protected.
    assert "frontmatter 里的 claims" in WIKI_APPLY_DESCRIPTION_ZH
    assert "元数据 frontmatter" not in WIKI_APPLY_DESCRIPTION_ZH


def test_the_chinese_ingest_text_names_the_compile_queue() -> None:
    # The ingest reply says "Compilation queued."; no index queue exists to read the text against.
    assert "编译队列" in WIKI_INGEST_DESCRIPTION_ZH
    assert "索引队列" not in WIKI_INGEST_DESCRIPTION_ZH
