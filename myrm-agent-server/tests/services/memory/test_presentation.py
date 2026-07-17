"""Unit tests for memory presentation (DTO projection) layer.

Covers memory_to_item conversion for all memory types with focus on
source_chat_id / source_message_id projection correctness.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from myrm_agent_harness.toolkits.memory import MemoryStatus, MemoryType
from myrm_agent_harness.toolkits.memory.types import (
    ClaimMemory,
    ConversationMemory,
    EpisodicMemory,
    IntegrationMemory,
    ProceduralMemory,
    ProfileEntry,
    SemanticMemory,
    ToolRulePriority,
)

from app.services.memory.presentation import memory_to_item, parse_memory_type


class TestParseMemoryType:
    def test_valid_types(self) -> None:
        for raw, expected in [
            ("semantic", MemoryType.SEMANTIC),
            ("episodic", MemoryType.EPISODIC),
            ("procedural", MemoryType.PROCEDURAL),
            ("profile", MemoryType.PROFILE),
            ("conversation", MemoryType.CONVERSATION),
            ("claim", MemoryType.CLAIM),
            ("task_digest", MemoryType.TASK_DIGEST),
            ("integration", MemoryType.INTEGRATION),
        ]:
            assert parse_memory_type(raw) == expected

    def test_invalid_type_raises_400(self) -> None:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            parse_memory_type("invalid_type")
        assert exc_info.value.status_code == 400


class TestSourceChatIdProjection:
    """Source chat/message ID projection — the core of this task."""

    def test_semantic_memory_with_source(self) -> None:
        mem = SemanticMemory(
            content="user likes Python",
            source_chat_id="conv-abc",
            source_message_id="msg-123",
        )
        item = memory_to_item(mem, MemoryType.SEMANTIC)
        assert item.source_chat_id == "conv-abc"
        assert item.source_message_id == "msg-123"

    def test_semantic_memory_without_source(self) -> None:
        mem = SemanticMemory(content="old data without source")
        item = memory_to_item(mem, MemoryType.SEMANTIC)
        assert item.source_chat_id is None
        assert item.source_message_id is None

    def test_episodic_memory_with_source(self) -> None:
        mem = EpisodicMemory(
            content="user completed task",
            source_chat_id="conv-xyz",
            source_message_id="msg-456",
        )
        item = memory_to_item(mem, MemoryType.EPISODIC)
        assert item.source_chat_id == "conv-xyz"
        assert item.source_message_id == "msg-456"

    def test_episodic_memory_without_source(self) -> None:
        mem = EpisodicMemory(content="event without source", event_type="action")
        item = memory_to_item(mem, MemoryType.EPISODIC)
        assert item.source_chat_id is None
        assert item.source_message_id is None

    def test_conversation_memory_with_source(self) -> None:
        mem = ConversationMemory(
            content="summary of exchange",
            raw_exchange="User: hello\nAI: hi",
            source_chat_id="conv-999",
            source_message_id="msg-888",
        )
        item = memory_to_item(mem, MemoryType.CONVERSATION)
        assert item.source_chat_id == "conv-999"
        assert item.source_message_id == "msg-888"

    def test_conversation_memory_without_source(self) -> None:
        mem = ConversationMemory(
            content="old conv summary",
            raw_exchange="User: bye\nAI: see you",
        )
        item = memory_to_item(mem, MemoryType.CONVERSATION)
        assert item.source_chat_id is None
        assert item.source_message_id is None

    def test_profile_entry_no_source(self) -> None:
        mem = ProfileEntry(key="name", value="Alice")
        item = memory_to_item(mem, MemoryType.PROFILE)
        assert item.source_chat_id is None
        assert item.source_message_id is None

    def test_procedural_memory_no_source(self) -> None:
        mem = ProceduralMemory(
            content="rule",
            trigger="when user says hi",
            action="greet back",
        )
        item = memory_to_item(mem, MemoryType.PROCEDURAL)
        assert item.source_chat_id is None
        assert item.source_message_id is None

    def test_empty_source_chat_id_not_projected(self) -> None:
        mem = SemanticMemory(
            content="test",
            source_chat_id="",
            source_message_id="msg-orphan",
        )
        item = memory_to_item(mem, MemoryType.SEMANTIC)
        assert item.source_chat_id is None
        assert item.source_message_id is None

    def test_source_message_without_chat_not_projected(self) -> None:
        mem = SemanticMemory(
            content="test",
            source_chat_id=None,
            source_message_id="msg-orphan",
        )
        item = memory_to_item(mem, MemoryType.SEMANTIC)
        assert item.source_chat_id is None
        assert item.source_message_id is None

    def test_source_chat_without_message(self) -> None:
        mem = SemanticMemory(
            content="test",
            source_chat_id="conv-only",
            source_message_id=None,
        )
        item = memory_to_item(mem, MemoryType.SEMANTIC)
        assert item.source_chat_id == "conv-only"
        assert item.source_message_id is None

    def test_semantic_with_correction_and_source_coexist(self) -> None:
        """correction_of + source_chat_id should both project without conflict."""
        mem = SemanticMemory(
            content="corrected fact",
            correction_of="old-mem-id",
            source_error="original was wrong",
            source_chat_id="conv-fix",
            source_message_id="msg-fix",
        )
        item = memory_to_item(mem, MemoryType.SEMANTIC)
        assert item.correction_of == "old-mem-id"
        assert item.source_error == "original was wrong"
        assert item.source_chat_id == "conv-fix"
        assert item.source_message_id == "msg-fix"

    def test_integration_memory_no_source_field(self) -> None:
        """IntegrationMemory has no source_chat_id field — getattr returns None."""
        mem = IntegrationMemory(
            content="gmail data",
            provider="gmail",
            account_key="user@test.com",
        )
        item = memory_to_item(mem, MemoryType.INTEGRATION)
        assert item.source_chat_id is None
        assert item.source_message_id is None


class TestBaseFieldProjection:
    """Verify base fields are correctly projected for every memory type."""

    def test_semantic_base_fields(self) -> None:
        now = datetime.now(timezone.utc)
        mem = SemanticMemory(
            content="knowledge fact",
            importance=0.8,
            confidence=0.9,
            created_at=now,
            updated_at=now,
            tags=["python", "coding"],
        )
        item = memory_to_item(mem, MemoryType.SEMANTIC)
        assert item.memory_type == "semantic"
        assert item.content == "knowledge fact"
        assert item.importance == 0.8
        assert item.confidence == 0.9
        assert item.tags == ["python", "coding"]
        assert item.projected_category == "knowledge"

    def test_procedural_fields(self) -> None:
        mem = ProceduralMemory(
            content="rule content",
            trigger="on request",
            action="do action",
            tool_name="search",
        )
        item = memory_to_item(mem, MemoryType.PROCEDURAL)
        assert item.trigger == "on request"
        assert item.action == "do action"
        assert item.tool_name == "search"
        assert item.projected_category == "method"

    def test_procedural_with_priority_and_lock(self) -> None:
        mem = ProceduralMemory(
            content="pinned rule",
            trigger="always",
            action="do critical thing",
            tool_name="code_gen",
            tool_rule_priority=ToolRulePriority.CRITICAL,
            is_user_locked=True,
            reasoning="user explicit request",
            application="all contexts",
        )
        item = memory_to_item(mem, MemoryType.PROCEDURAL)
        assert item.tool_rule_priority == "critical"
        assert item.reasoning == "user explicit request"
        assert item.application == "all contexts"

    def test_episodic_fields(self) -> None:
        mem = EpisodicMemory(
            content="event happened",
            event_type="user_action",
            related_entities=["entity_a"],
        )
        item = memory_to_item(mem, MemoryType.EPISODIC)
        assert item.event_type == "user_action"
        assert item.related_entities == ["entity_a"]
        assert item.projected_category == "experience"

    def test_profile_entry_fields(self) -> None:
        mem = ProfileEntry(key="language", value="zh")
        item = memory_to_item(mem, MemoryType.PROFILE)
        assert item.key == "language"
        assert item.value == "zh"
        assert item.projected_category == "user_profile"

    def test_conversation_projection_category(self) -> None:
        mem = ConversationMemory(content="test conv", raw_exchange="Q: hi\nA: hello")
        item = memory_to_item(mem, MemoryType.CONVERSATION)
        assert item.projected_category == "dialogue"
        assert item.projected_label == "Dialogue Memory"

    def test_claim_projection_category(self) -> None:
        mem = ClaimMemory(
            content="verified claim",
            claim_key="capital-france",
            title="Capital of France",
            claim_text="Paris is the capital of France",
        )
        item = memory_to_item(mem, MemoryType.CLAIM)
        assert item.projected_category == "verified_knowledge"
        assert item.projected_label == "Verified Knowledge"

    def test_integration_projection_category(self) -> None:
        mem = IntegrationMemory(
            content="github PR data",
            provider="github",
            account_key="user",
        )
        item = memory_to_item(mem, MemoryType.INTEGRATION)
        assert item.projected_category == "other"

    def test_status_archived_projected(self) -> None:
        mem = SemanticMemory(content="archived fact", status=MemoryStatus.ARCHIVED)
        item = memory_to_item(mem, MemoryType.SEMANTIC)
        assert item.status == "archived"

    def test_status_disabled_projected(self) -> None:
        mem = SemanticMemory(content="disabled fact", status=MemoryStatus.DISABLED)
        item = memory_to_item(mem, MemoryType.SEMANTIC)
        assert item.status == "disabled"

    def test_metadata_preserved(self) -> None:
        meta = {"custom_key": "custom_val", "priority": 1}
        mem = SemanticMemory(content="with meta", metadata=meta)
        item = memory_to_item(mem, MemoryType.SEMANTIC)
        assert item.metadata["custom_key"] == "custom_val"
        assert item.metadata["priority"] == 1

    def test_empty_tags_default(self) -> None:
        mem = SemanticMemory(content="no tags")
        item = memory_to_item(mem, MemoryType.SEMANTIC)
        assert item.tags == []

    def test_episodic_empty_related_entities(self) -> None:
        mem = EpisodicMemory(content="solo event", event_type="test")
        item = memory_to_item(mem, MemoryType.EPISODIC)
        assert item.related_entities == []
