"""Tests for Exact Fact Deterministic Hard Lock and Dual-Track Search.

Covers:
- ExactFactClassifier identification (UUID, Git SHA, SemVer, Port, Config Key)
- False positive suppression
- BaseMemory.is_user_protected and ForgettingStrategy immunity
- SQLiteRelationalStore exact fact persistence, search_fts5, and deletion
- MemoryRetriever deterministic exact-fact boosting
- MemoryWriter write-time exact fact recognition
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.memory.relational.sqlite_store import SQLiteRelationalStore
from myrm_agent_harness.toolkits.memory.retriever import MemoryRetriever
from myrm_agent_harness.toolkits.memory.strategies.exact_fact import ExactFactClassifier
from myrm_agent_harness.toolkits.memory.strategies.forgetting import ForgettingStrategy
from myrm_agent_harness.toolkits.memory.types import (
    MemorySearchResult,
    MemoryType,
    SemanticMemory,
)


class TestExactFactClassifier:
    def test_uuid_extraction(self) -> None:
        text = "The host identifier is 123e4567-e89b-12d3-a456-426614174000 in cluster."
        identifiers = ExactFactClassifier.extract_identifiers(text)
        assert "123e4567-e89b-12d3-a456-426614174000" in identifiers
        is_exact, idents = ExactFactClassifier.classify(text)
        assert is_exact is True
        assert "123e4567-e89b-12d3-a456-426614174000" in idents

    def test_git_sha_extraction(self) -> None:
        text = "Rolled back release to git commit a1b2c3d4e5f60718293a4b5c6d7e8f9012345678 due to bug."
        identifiers = ExactFactClassifier.extract_identifiers(text)
        assert "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678" in identifiers
        is_exact, idents = ExactFactClassifier.classify(text)
        assert is_exact is True
        assert "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678" in idents

    def test_semver_extraction(self) -> None:
        text = "Upgraded runtime dependency to v2.14.3-alpha.1 successfully."
        identifiers = ExactFactClassifier.extract_identifiers(text)
        assert any("2.14.3" in ident for ident in identifiers)
        is_exact, idents = ExactFactClassifier.classify(text)
        assert is_exact is True
        assert any("2.14.3" in ident for ident in idents)

    def test_port_and_endpoint_extraction(self) -> None:
        text = "Internal telemetry collector is listening on port :9090 or localhost:8080."
        identifiers = ExactFactClassifier.extract_identifiers(text)
        assert any("9090" in ident or "8080" in ident for ident in identifiers)
        is_exact, _idents = ExactFactClassifier.classify(text)
        assert is_exact is True

    def test_config_key_extraction(self) -> None:
        text = "Please set API_GATEWAY_TIMEOUT_MS and DATABASE_MAX_CONNECTIONS in .env."
        identifiers = ExactFactClassifier.extract_identifiers(text)
        assert "API_GATEWAY_TIMEOUT_MS" in identifiers
        assert "DATABASE_MAX_CONNECTIONS" in identifiers
        is_exact, idents = ExactFactClassifier.classify(text)
        assert is_exact is True
        assert "API_GATEWAY_TIMEOUT_MS" in idents

    @pytest.mark.parametrize(
        ("spaced", "attached"),
        [
            ("服务器地址是 10.0.0.5:8080 ，请记住", "服务器地址是10.0.0.5:8080，请记住"),
            ("版本 v2.4.1 上线", "版本v2.4.1上线"),
            ("把 DEPLOY_TOKEN 设置为 abc", "把DEPLOY_TOKEN设置为abc"),
            ("订单号 123e4567-e89b-12d3-a456-426614174000 已发货", "订单号123e4567-e89b-12d3-a456-426614174000已发货"),
            ("我的数据库在 localhost:5432 上", "我的数据库在localhost:5432上"),
            ("commit 是 a1b2c3d4e 修复", "commit是a1b2c3d4e修复"),
        ],
    )
    def test_cjk_neighbours_do_not_hide_an_identifier(self, spaced: str, attached: str) -> None:
        """Chinese is written without spaces, so an identifier must be found with or without them."""
        found = ExactFactClassifier.extract_identifiers(spaced)
        assert found
        assert ExactFactClassifier.extract_identifiers(attached) == found

    def test_an_address_next_to_cjk_text_is_not_cut_into_a_fragment(self) -> None:
        assert ExactFactClassifier.extract_identifiers("服务器地址是10.0.0.5:8080，请记住") == ["10.0.0.5:8080"]

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("10.0.0.5:8080", ["10.0.0.5:8080"]),
            ("connect to 192.168.1.100", ["192.168.1.100"]),
            ("hosts 10.0.0.5 and 10.0.0.6:8080", ["10.0.0.5", "10.0.0.6:8080"]),
            ("0.0.0.0:80 and localhost:3000", ["0.0.0.0:80", "localhost:3000"]),
            ("build 1.2.3.4 shipped", ["1.2.3.4"]),
        ],
    )
    def test_an_address_is_one_identifier_as_written(self, text: str, expected: list[str]) -> None:
        """No version-looking fragment (``10.0.0``) is read out of an address, or every host of a subnet would match."""
        assert ExactFactClassifier.extract_identifiers(text) == expected

    @pytest.mark.parametrize("text", ["10.0.0.256", "1.2.3.4.5", "ip10.0.0.5", "999.1.1.1:80"])
    def test_a_dotted_number_that_is_no_address_is_no_identifier(self, text: str) -> None:
        assert ExactFactClassifier.extract_identifiers(text) == []

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("version 2.3.1 released", ["2.3.1"]),
            ("see release 1.2.3.", ["1.2.3"]),
            ("libfoo-1.2.3.tar.gz", ["1.2.3"]),
            ("v1.2.3-rc.1+build.5", ["v1.2.3-rc.1+build.5"]),
        ],
    )
    def test_a_version_is_extracted_whole(self, text: str, expected: list[str]) -> None:
        assert ExactFactClassifier.extract_identifiers(text) == expected

    @pytest.mark.parametrize("text", ["服务器端口 8080 已开放", "服务器端口：8080已开放", "端口\u30008080开放"])
    def test_a_chinese_port_declaration_is_extracted(self, text: str) -> None:
        assert ExactFactClassifier.extract_identifiers(text) == ["8080"]

    @pytest.mark.parametrize("text", ["第3章讲了10.5个例子", "这个方案比上一版快了3.5倍", "会议在下午3点开始"])
    def test_cjk_text_with_plain_numbers_is_not_an_exact_fact(self, text: str) -> None:
        assert ExactFactClassifier.extract_identifiers(text) == []

    def test_common_text_no_false_positive(self) -> None:
        text = "We should meet tomorrow afternoon to discuss product design requirements."
        identifiers = ExactFactClassifier.extract_identifiers(text)
        assert len(identifiers) == 0
        is_exact, idents = ExactFactClassifier.classify(text)
        assert is_exact is False
        assert len(idents) == 0

    def test_metadata_override_and_short_text(self) -> None:
        assert ExactFactClassifier.is_exact_fact("", metadata={"is_exact_fact": True}) is True
        assert (
            ExactFactClassifier.is_exact_fact(
                "UUID 123e4567-e89b-12d3-a456-426614174000",
                metadata={"is_exact_fact": False},
            )
            is False
        )
        assert ExactFactClassifier.classify("", metadata={"is_exact_fact": True})[0] is True
        assert ExactFactClassifier.extract_identifiers("hi") == []
        assert ExactFactClassifier.extract_identifiers("") == []


class TestExactFactMemoryProtection:
    def test_base_memory_protection_flag(self) -> None:
        m = SemanticMemory(content="Regular preference", is_exact_fact=False)
        assert not m.is_user_protected

        m_exact = SemanticMemory(
            content="Host uuid 123e4567-e89b-12d3-a456-426614174000",
            is_exact_fact=True,
            exact_identifiers=["123e4567-e89b-12d3-a456-426614174000"],
        )
        assert m_exact.is_user_protected is True

    def test_forgetting_strategy_immunity(self) -> None:
        strategy = ForgettingStrategy()
        m = SemanticMemory(
            content="Host uuid 123e4567-e89b-12d3-a456-426614174000",
            importance=0.001,
            access_count=0,
            created_at=datetime.now(UTC) - timedelta(days=500),
            is_exact_fact=True,
        )
        result = strategy.calculate_retention_score(m)
        assert not result.should_forget
        assert "Protected" in result.reason


@pytest.mark.asyncio
class TestExactFactSQLiteStore:
    async def test_record_search_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test_memory.db")
            store = SQLiteRelationalStore(db_path=db_path)

            memory_id = "mem_fact_001"
            content = "Production server uuid 123e4567-e89b-12d3-a456-426614174000 is online on port 9090."
            identifiers = ["123e4567-e89b-12d3-a456-426614174000", "9090"]

            # Record exact fact
            await store.record_exact_fact(
                memory_id=memory_id,
                user_id="user_test",
                content=content,
                identifiers=identifiers,
                primary_namespace="ops",
            )

            # Search exact identifier
            results = await store.search_fts5("123e4567-e89b-12d3-a456-426614174000", limit=5)
            assert len(results) >= 1
            assert results[0].id == memory_id
            assert results[0].memory.is_exact_fact is True
            assert "123e4567-e89b-12d3-a456-426614174000" in results[0].memory.exact_identifiers

            # Search non-matching
            no_results = await store.search_fts5("non_existing_random_sha_or_uuid", limit=5)
            assert len(no_results) == 0

            # Delete
            await store.delete_exact_fact(memory_id)

            # Search after deletion
            results_after = await store.search_fts5("123e4567-e89b-12d3-a456-426614174000", limit=5)
            assert len(results_after) == 0

            await store.close()

    @pytest.mark.asyncio
    async def test_record_exact_fact_empty_identifiers_and_fts_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test_memory_edge.db")
            store = SQLiteRelationalStore(db_path=db_path)

            # Record with empty identifiers -> should safely return without error
            await store.record_exact_fact(
                memory_id="empty_fact",
                user_id="user_test",
                content="Just some regular text",
                identifiers=[],
            )

            # Record with text and test FTS5 fallback query
            await store.record_exact_fact(
                memory_id="fts_fallback_fact",
                user_id="user_test",
                content="SpecialKeywordKubernetesDeploymentCluster",
                identifiers=["9090"],
            )
            # Query word in content that triggers FTS5 fallback search
            results = await store.search_fts5("SpecialKeywordKubernetesDeploymentCluster", limit=5)
            assert any(r.id == "fts_fallback_fact" for r in results)

            # Delete non-existing ID should not raise
            await store.delete_exact_fact("non_existing_id")
            await store.close()


class TestRetrieverExactFactBoosting:
    def test_boost_exact_fact_top_rank(self) -> None:
        retriever = MemoryRetriever()

        exact_mem = SemanticMemory(
            id="exact_1",
            content="Host uuid 123e4567-e89b-12d3-a456-426614174000 on node-0",
            is_exact_fact=True,
            exact_identifiers=["123e4567-e89b-12d3-a456-426614174000"],
        )
        vague_mem = SemanticMemory(
            id="vague_2",
            content="Some generic cloud server information and guidelines",
            importance=0.99,
        )

        r_exact = MemorySearchResult(memory=exact_mem, score=0.6, memory_type=MemoryType.SEMANTIC)
        r_vague = MemorySearchResult(memory=vague_mem, score=0.95, memory_type=MemoryType.SEMANTIC)

        fused = retriever.fuse(
            [[r_vague, r_exact]],
            limit=2,
            query="What is the IP of host 123e4567-e89b-12d3-a456-426614174000?",
        )

        assert len(fused) == 2
        # Exact fact must be ranked #1 due to deterministic hard lock boost
        assert fused[0].id == "exact_1"
        assert fused[0].memory.is_exact_fact is True


@pytest.mark.asyncio
class TestMemoryManagerExactFactEndToEnd:
    async def test_manager_write_exact_fact_and_delete_cascade(
        self,
        memory_config,
        mock_vector_store,
        mock_embedding,
    ) -> None:
        from myrm_agent_harness.toolkits.memory.manager import MemoryManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test_memory.db")
            store = SQLiteRelationalStore(db_path=db_path)
            manager = MemoryManager(
                memory_config,
                user_id="user_admin",
                vector=mock_vector_store,
                embedding=mock_embedding,
                relational=store,
                fts5_searcher=store.search_fts5,
            )

            # Store memory containing exact UUID
            mem = await manager.store(
                SemanticMemory(
                    content="Critical cluster coordinator node uuid 123e4567-e89b-12d3-a456-426614174000 port 9090",
                )
            )

            assert mem.is_exact_fact is True
            assert "123e4567-e89b-12d3-a456-426614174000" in mem.exact_identifiers
            assert mem.is_user_protected is True

            # Direct FTS5 search
            fts_hits = await store.search_fts5("123e4567-e89b-12d3-a456-426614174000", limit=5)
            assert len(fts_hits) >= 1
            assert fts_hits[0].id == mem.id

            # Delete memory and assert cascade cleanup
            from myrm_agent_harness.toolkits.vector.base import VectorDocument

            mock_vector_store.get.return_value = [
                VectorDocument(
                    id=mem.id,
                    content=mem.content,
                    vector=[0.1] * 768,
                    metadata={
                        "user_id": "user_admin",
                        "primary_namespace": "agent:default",
                        "namespaces": ["global", "agent:default"],
                    },
                )
            ]
            await manager.delete_memory(manager._config.semantic_collection, [mem.id])
            fts_hits_after = await store.search_fts5("123e4567-e89b-12d3-a456-426614174000", limit=5)
            assert len(fts_hits_after) == 0

            await manager.close()

    @pytest.mark.asyncio
    async def test_memory_manager_fts5_auto_binding(
        self,
        memory_config,
        mock_vector_store,
        mock_embedding,
    ) -> None:
        from myrm_agent_harness.toolkits.memory.manager import MemoryManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test_auto_bind.db")
            store = SQLiteRelationalStore(db_path=db_path)

            # Deliberately omit fts5_searcher to test auto-binding from relational
            manager = MemoryManager(
                memory_config,
                user_id="user_auto",
                vector=mock_vector_store,
                embedding=mock_embedding,
                relational=store,
            )
            assert manager._fts5_searcher is not None
            assert manager._search_service._fts5_searcher is not None

            # Store memory containing exact UUID
            mem = await manager.store(
                SemanticMemory(
                    content="Server port is 15432 and instance id is a3b8c2d1-9f4e-48a2-b91c-8e4d3c2b1a0f",
                )
            )
            assert mem.is_exact_fact is True
            assert "a3b8c2d1-9f4e-48a2-b91c-8e4d3c2b1a0f" in mem.exact_identifiers

            # Direct search via auto-bound fts5_searcher
            fts_hits = await manager._fts5_searcher("a3b8c2d1-9f4e-48a2-b91c-8e4d3c2b1a0f", limit=5)
            assert len(fts_hits) >= 1
            assert fts_hits[0].id == mem.id
            assert "15432" in fts_hits[0].content

            await manager.close()
