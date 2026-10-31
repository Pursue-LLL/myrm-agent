"""One question always becomes one index query: the query terms are picked by their position in the question.

[INPUT]
- app.services.wiki.knowledge_pack.selector::resolve_proactive_snippets_from_vaults, tokenize_text
- myrm_agent_harness.toolkits.retriever.cjk_tokenizer::build_cjk_index_segment (POS: writes the CJK search column the way the index does)

[OUTPUT]
- Tests that a question with more than eight terms searches its first eight, in the same order in every process, and
  that ``tokenize_text`` still returns each term once.

[POS]
Term-selection counterpart of the index-backed cases in ``test_knowledge_pack.py``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.retriever.cjk_tokenizer import build_cjk_index_segment

from app.services.wiki.knowledge_pack.selector import resolve_proactive_snippets_from_vaults, tokenize_text


def test_tokenize_text_returns_each_term_once() -> None:
    """Words and CJK unigrams/bigrams come back as a set, however often they repeat."""
    assert tokenize_text("Docker 部署 docker") == {"docker", "部", "署", "部署"}
    assert tokenize_text("") == set()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "kept_page", "dropped_page"),
    [
        (
            "zulu yankee xray whiskey victor uniform tango sierra romeo quebec papa oscar",
            "zulu yankee field notes",
            "papa oscar field notes",
        ),
        (
            "zulu zulu zulu yankee xray whiskey victor uniform tango sierra romeo",
            "sierra field notes",
            "romeo field notes",
        ),
        ("帮我总结一下上周关于向量数据库选型", "总结一下上周的会议纪要", "数据库选型方案对比"),
    ],
    ids=["english", "english-repeated-words", "chinese"],
)
async def test_index_search_uses_the_first_eight_terms_of_a_long_query(
    tmp_path: Path, query: str, kept_page: str, dropped_page: str
) -> None:
    """A query with more than eight terms searches its first eight, the same eight in every process."""
    with sqlite3.connect(tmp_path / ".wiki_index.db") as conn:
        conn.execute(
            'CREATE VIRTUAL TABLE wiki_fts USING fts5(concept_name, truth_content, tokenize="unicode61 remove_diacritics 1")'
        )
        conn.executemany(
            "INSERT INTO wiki_fts(concept_name, truth_content) VALUES (?, ?)",
            [
                ("KeptPage", build_cjk_index_segment(kept_page)),
                ("DroppedPage", build_cjk_index_segment(dropped_page)),
            ],
        )

    result = await resolve_proactive_snippets_from_vaults(
        query=query,
        vault_paths=(tmp_path,),
        vault_labels={str(tmp_path): "kb"},
        timeout_seconds=1.0,
    )

    assert [snippet.article_title for snippet in result.snippets] == ["KeptPage"]
