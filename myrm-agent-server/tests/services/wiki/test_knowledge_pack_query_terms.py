"""One question always becomes one index query: its terms are the first sixteen that are not stop words, in order.

[INPUT]
- app.services.wiki.knowledge_pack.query_terms::search_terms, tokenize_text
- app.services.wiki.knowledge_pack.selector::resolve_proactive_snippets_from_vaults
- myrm_agent_harness.toolkits.retriever.cjk_tokenizer::build_cjk_index_segment (POS: writes the CJK search column the way the index does)

[OUTPUT]
- Tests that the search terms skip stop words before the cap, keep the order of the question, use single characters
  only when nothing longer is left, and that a long question searches the index by exactly those terms.

[POS]
Term-selection counterpart of the index-backed cases in ``test_knowledge_pack.py``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.retriever.cjk_tokenizer import build_cjk_index_segment

from app.services.wiki.knowledge_pack.query_terms import search_terms, tokenize_text
from app.services.wiki.knowledge_pack.selector import resolve_proactive_snippets_from_vaults


def test_tokenize_text_returns_each_term_once() -> None:
    """Words and CJK unigrams/bigrams come back as a set, however often they repeat."""
    assert tokenize_text("Docker 部署 docker") == {"docker", "部", "署", "部署"}
    assert tokenize_text("") == set()


def test_search_terms_drop_stop_words_before_the_cap() -> None:
    """The filler of a polite question never takes a slot from its subject."""
    assert search_terms("what is the zulu protocol") == ["zulu", "protocol"]
    assert search_terms("the " * 30 + "zulu yankee") == ["zulu", "yankee"]

    terms = search_terms("请问什么是向量数据库")
    assert "什么" not in terms
    assert terms.index("向量") < terms.index("数据") < terms.index("据库")


def test_search_terms_keep_question_order_and_stop_at_sixteen() -> None:
    """The first sixteen terms by position, so one question gives one query in every process."""
    words = [f"w{i:02d}x" for i in range(20)]

    assert search_terms(" ".join(words)) == words[:16]
    assert search_terms(" ".join(reversed(words))) == list(reversed(words))[:16]


def test_search_terms_use_single_characters_only_when_nothing_longer_is_left() -> None:
    assert search_terms("税") == ["税"]
    assert search_terms("税 hello") == ["hello"]
    assert search_terms("what is it") == []
    assert search_terms("的") == []
    assert search_terms("") == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "kept_page", "dropped_page"),
    [
        (
            "zulu yankee xray whiskey victor uniform tango sierra romeo quebec papa oscar november mike lima kilo juliet india hotel golf",
            "zulu yankee xray field notes",
            "juliet india hotel golf field notes",
        ),
        (
            "zulu zulu zulu yankee xray whiskey victor uniform tango sierra romeo quebec papa oscar november mike lima kilo juliet india hotel golf",
            "kilo lima mike field notes",
            "juliet india hotel field notes",
        ),
        ("帮我总结一下上周关于向量数据库选型的会议纪要", "总结一下上周的工作安排", "会议纪要整理"),
    ],
    ids=["english", "english-repeated-words", "chinese"],
)
async def test_index_search_uses_the_first_sixteen_search_terms_of_a_long_query(
    tmp_path: Path, query: str, kept_page: str, dropped_page: str
) -> None:
    """A query with more than sixteen terms searches its first sixteen, the same sixteen in every process."""
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
