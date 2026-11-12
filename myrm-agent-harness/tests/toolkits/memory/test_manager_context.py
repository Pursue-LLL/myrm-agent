"""Tests for MemoryManager context loading and convenience methods."""

from datetime import UTC, datetime

import pytest

from myrm_agent_harness.toolkits.memory._internal.storage import (
    MemoryError,
    MemoryNotFoundError,
)
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.types import (
    EpisodicMemory,
    ProceduralMemory,
    SemanticMemory,
)


class TestContextLoading:
    """Test get_context operation."""

    @pytest.mark.asyncio
    async def test_get_context_with_all_components(
        self, mock_relational_store, memory_config
    ):
        """Test get_context includes all requested components."""
        mock_relational_store.list_profiles.return_value = [("key1", "value1")]
        mock_relational_store.list_rules.return_value = []

        manager = MemoryManager(
            memory_config, user_id="test_user", relational=mock_relational_store
        )

        context = await manager.get_context(include_profile=True, include_rules=True)

        assert "global_profile" in context
        assert "peer_profile" in context
        assert "rules" in context
        assert mock_relational_store.list_profiles.await_args.kwargs["namespaces"] == [
            "global",
            "agent:default",
        ]
        assert mock_relational_store.list_rules.await_args.kwargs["namespaces"] == [
            "global",
            "agent:default",
        ]

    @pytest.mark.asyncio
    async def test_get_context_without_relational(
        self, mock_vector_store, mock_embedding, memory_config
    ):
        """Test get_context returns default structure when no relational backend."""
        manager = MemoryManager(
            memory_config,
            user_id="test_user",
            vector=mock_vector_store,
            embedding=mock_embedding,
        )

        context = await manager.get_context()

        assert "global_profile" in context
        assert "peer_profile" in context
        assert "rules" in context
        assert context["global_profile"] == {}
        assert context["peer_profile"] == {}
        assert context["rules"] == []


class TestConvenienceMethods:
    """Test convenience methods like add_knowledge, add_event, add_rule."""

    @pytest.mark.asyncio
    async def test_add_knowledge(
        self, mock_vector_store, mock_embedding, memory_config
    ):
        """Test add_knowledge convenience method."""
        mock_vector_store.upsert.return_value = ["mem-1"]

        manager = MemoryManager(
            memory_config,
            user_id="test_user",
            vector=mock_vector_store,
            embedding=mock_embedding,
        )

        result = await manager.add_knowledge(
            "Python is a programming language", importance=0.8, tags=["programming"]
        )

        assert isinstance(result, SemanticMemory)
        assert result.content == "Python is a programming language"
        assert result.importance == 0.8

    @pytest.mark.asyncio
    async def test_add_event(self, mock_vector_store, mock_embedding, memory_config):
        """Test add_event convenience method."""
        mock_vector_store.upsert.return_value = ["mem-2"]

        manager = MemoryManager(
            memory_config,
            user_id="test_user",
            vector=mock_vector_store,
            embedding=mock_embedding,
        )

        result = await manager.add_event(
            "User asked about Python",
            event_type="question",
            related_entities=["Python"],
        )

        assert isinstance(result, EpisodicMemory)
        assert result.content == "User asked about Python"
        assert result.event_type == "question"

    @pytest.mark.asyncio
    async def test_add_rule(self, mock_relational_store, memory_config):
        """Test add_rule convenience method."""
        rule_obj = ProceduralMemory(
            id="rule-1",
            content="When: trigger → Do: action",
            trigger="trigger",
            action="action",
        )
        mock_relational_store.create_rule.return_value = rule_obj

        manager = MemoryManager(
            memory_config, user_id="test_user", relational=mock_relational_store
        )

        result = await manager.add_rule(trigger="user asks weather", action="call weather_api")

        assert isinstance(result, ProceduralMemory)
        assert result.id == "rule-1"


class TestCorrectMemory:
    """Test memory correction workflow."""

    @pytest.mark.asyncio
    async def test_correct_semantic_memory(
        self, mock_vector_store, mock_embedding, memory_config
    ):
        """Test correcting a factually wrong semantic memory."""
        from myrm_agent_harness.toolkits.memory.protocols.vector import VectorDocument

        existing_doc = VectorDocument(
            id="mem-1",
            content="Paris is the capital of Germany",
            vector=[0.1] * 768,
            metadata={
                "memory_type": "semantic",
                "importance": 0.7,
                "confidence": 1.0,
                "source_chat_id": "",
                "preference_type": "",
                "preference_strength": 0.0,
                "correction_of": "",
                "access_count": 5,
            },
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_vector_store.get.return_value = [existing_doc]
        mock_vector_store.upsert.return_value = ["mem-new"]

        manager = MemoryManager(
            memory_config,
            user_id="test_user",
            vector=mock_vector_store,
            embedding=mock_embedding,
        )

        correction = await manager.correct_memory(
            "mem-1", "Paris is the capital of France"
        )

        assert isinstance(correction, SemanticMemory)
        assert correction.content == "Paris is the capital of France"
        assert correction.correction_of == "mem-1"
        assert correction.importance > 0.7
        assert mock_vector_store.upsert.call_count == 2

    @pytest.mark.asyncio
    async def test_correct_nonexistent_memory_raises_error(
        self, mock_vector_store, mock_embedding, memory_config
    ):
        """Test correcting non-existent memory raises error."""
        mock_vector_store.get.return_value = None

        manager = MemoryManager(
            memory_config,
            user_id="test_user",
            vector=mock_vector_store,
            embedding=mock_embedding,
        )

        with pytest.raises(MemoryNotFoundError, match="Memory mem-1 not found"):
            await manager.correct_memory("mem-1", "Corrected content")

    @pytest.mark.asyncio
    async def test_correct_non_semantic_raises_error(
        self, mock_relational_store, memory_config
    ):
        """Test correcting non-semantic memory raises error."""
        rule = ProceduralMemory(
            id="rule-1", content="Test rule", trigger="trigger", action="action"
        )
        mock_relational_store.get_rule.return_value = rule

        manager = MemoryManager(
            memory_config, user_id="test_user", relational=mock_relational_store
        )

        with pytest.raises(
            MemoryError, match="Correction only supports SemanticMemory"
        ):
            await manager.correct_memory("rule-1", "Corrected")
