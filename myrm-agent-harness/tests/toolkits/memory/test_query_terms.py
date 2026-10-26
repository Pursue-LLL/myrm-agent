"""Query-side function-word pruning: unit behaviour and mirror ranking on embedded Qdrant."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from myrm_agent_harness.toolkits.memory._internal.bm25_sparse_encoding import (
    content_to_sparse,
    query_to_sparse,
    token_index,
)
from myrm_agent_harness.toolkits.memory._internal.bm25_sparse_index import wrap_with_bm25_sparse_index
from myrm_agent_harness.toolkits.memory._internal.query_terms import prune_function_words
from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.protocols.vector import VectorDocument
from myrm_agent_harness.toolkits.retriever.bm25_retrieval import preprocess_text

CONFIG = MemoryConfig(embedding_model="test-model", collection_prefix="qt")


class TestPruneFunctionWords:
    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("what did I say about the release plan before", ["release", "plan"]),
            ("我之前跟你说过的关于发布计划的事情是怎么来着", ["发布", "计划"]),
        ],
    )
    def test_conversational_query_keeps_content_terms(self, query: str, expected: list[str]) -> None:
        assert prune_function_words(preprocess_text(query)) == expected

    def test_negations_are_kept(self) -> None:
        assert prune_function_words(["do", "not", "like", "coffee"]) == ["not", "like", "coffee"]
        assert prune_function_words(["用户", "不", "喜欢", "咖啡", "吗"]) == ["用户", "不", "喜欢", "咖啡"]

    def test_name_like_homographs_are_kept(self) -> None:
        assert prune_function_words(["will", "s", "birthday"]) == ["will", "birthday"]

    def test_uppercase_acronym_is_not_the_pronoun(self) -> None:
        assert prune_function_words(["IT", "it", "support"]) == ["IT", "support"]

    def test_all_function_words_fall_back_to_the_original_tokens(self) -> None:
        tokens = ["who", "are", "you"]
        assert prune_function_words(tokens) == tokens
        assert prune_function_words([]) == []


class TestQueryEncoding:
    def test_query_drops_function_words_but_documents_keep_them(self) -> None:
        assert query_to_sparse("what did I say about the release plan before") == query_to_sparse("release plan")
        doc_indices, _ = content_to_sparse("what did I say")
        assert token_index("what") in doc_indices

    def test_function_word_only_query_still_encodes(self) -> None:
        indices, values = query_to_sparse("who are you")
        assert len(indices) == 3
        assert values == [1.0, 1.0, 1.0]


def _doc(content: str) -> VectorDocument:
    now = datetime.now(UTC)
    return VectorDocument(
        id=str(uuid4()),
        content=content,
        vector=[0.1] * 8,
        metadata={"user_id": "u1", "memory_type": "semantic", "archived": False},
        created_at=now,
        updated_at=now,
    )


class TestMirrorRanking:
    """A filler-heavy decoy must not outrank the memory that shares the content terms.

    The corpus is tiny on purpose: the filler words occur in one document only, so a
    server-side IDF alone cannot tell them from content words.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("target", "decoy", "query"),
        [
            (
                "The release plan freezes the branch on Friday",
                "I asked what you said about the weather before",
                "what did I say about the release plan before",
            ),
            (
                "发布计划定在周五冻结代码",
                "我之前跟你说过的事情是怎么来着",
                "我之前跟你说过的关于发布计划的事情是怎么来着",
            ),
        ],
    )
    async def test_content_terms_outrank_filler_matches(
        self, tmp_path: Path, target: str, decoy: str, query: str
    ) -> None:
        from myrm_agent_harness.toolkits.vector.qdrant import create_embedded_store

        store = await create_embedded_store(path=str(tmp_path / "qdrant"))
        wrapped = wrap_with_bm25_sparse_index(store)
        try:
            await wrapped.upsert(
                CONFIG.semantic_collection,
                [_doc(target), _doc(decoy), _doc("unrelated note about coffee beans")],
            )
            await wrapped.bm25_backfill(CONFIG)

            hits = await wrapped.bm25_search(query, CONFIG)
            assert hits is not None
            assert hits[0].memory.content == target
        finally:
            await wrapped.close()
