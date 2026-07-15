"""Unit tests for import_chatgpt.py — ChatGPT conversations.json adapter.

Validates tree-mapping traversal, episodic entry generation, dedup metadata,
source detection, and edge-case handling.
"""

from __future__ import annotations

import pytest

from app.services.memory.import_adapters import build_memory_import_dry_run
from app.services.memory.import_chatgpt import (
    _extract_messages_from_mapping,
    _parse_conversations,
    dry_run_chatgpt,
    is_chatgpt_payload,
)


def _make_conversation(
    conv_id: str = "conv-abc",
    title: str = "Test Chat",
    create_time: float = 1700000000.0,
    messages: list[tuple[str, str]] | None = None,
) -> dict[str, object]:
    """Build a minimal ChatGPT conversation fixture with tree mapping."""

    if messages is None:
        messages = [("user", "Hello"), ("assistant", "Hi there!")]

    mapping: dict[str, dict[str, object]] = {}
    prev_id: str | None = None

    root_id = "root-node"
    mapping[root_id] = {"id": root_id, "message": None, "parent": None, "children": []}
    prev_id = root_id

    last_id = root_id
    for i, (role, content) in enumerate(messages):
        node_id = f"node-{i}"
        mapping[node_id] = {
            "id": node_id,
            "parent": prev_id,
            "children": [],
            "message": {
                "id": f"msg-{i}",
                "author": {"role": role},
                "content": {"content_type": "text", "parts": [content]},
                "create_time": create_time + i * 60,
            },
        }
        prev_id = node_id
        last_id = node_id

    return {
        "id": conv_id,
        "title": title,
        "create_time": create_time,
        "mapping": mapping,
        "current_node": last_id,
    }


class TestIsChatgptPayload:
    """Source detection for ChatGPT payloads."""

    def test_explicit_source_tag(self) -> None:
        assert is_chatgpt_payload({"_source": "chatgpt", "conversations": []})

    def test_structural_detection(self) -> None:
        conv = _make_conversation()
        assert is_chatgpt_payload({"conversations": [conv]})

    def test_rejects_empty_conversations(self) -> None:
        assert not is_chatgpt_payload({"conversations": []})

    def test_rejects_unrelated_payload(self) -> None:
        assert not is_chatgpt_payload({"sessions": [], "memories": []})


class TestExtractMessagesFromMapping:
    """Tree mapping traversal logic."""

    def test_extracts_user_and_assistant(self) -> None:
        conv = _make_conversation(messages=[("user", "Q1"), ("assistant", "A1"), ("user", "Q2")])
        msgs = _extract_messages_from_mapping(conv)
        assert len(msgs) == 3
        assert msgs[0] == {"role": "user", "content": "Q1"}
        assert msgs[1] == {"role": "assistant", "content": "A1"}
        assert msgs[2] == {"role": "user", "content": "Q2"}

    def test_skips_system_messages(self) -> None:
        conv = _make_conversation(messages=[("system", "You are helpful"), ("user", "Hi")])
        msgs = _extract_messages_from_mapping(conv)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

    def test_handles_missing_mapping(self) -> None:
        conv = {"title": "test", "current_node": "x"}
        msgs = _extract_messages_from_mapping(conv)
        assert msgs == []

    def test_handles_missing_current_node(self) -> None:
        conv = {"title": "test", "mapping": {"a": {"message": None, "parent": None}}}
        msgs = _extract_messages_from_mapping(conv)
        assert msgs == []

    def test_no_infinite_loop_on_cycle(self) -> None:
        mapping = {
            "a": {"id": "a", "parent": "b", "message": None},
            "b": {"id": "b", "parent": "a", "message": None},
        }
        conv = {"mapping": mapping, "current_node": "a"}
        msgs = _extract_messages_from_mapping(conv)
        assert isinstance(msgs, list)


class TestDryRunChatgpt:
    """Full dry-run adapter tests."""

    def test_basic_conversation_import(self) -> None:
        conv = _make_conversation(title="My Research")
        result = dry_run_chatgpt({"conversations": [conv]})

        assert result.summary.source == "chatgpt"
        assert result.summary.total_items == 1
        assert result.summary.mapped_items == 1
        assert result.summary.status == "ready"
        assert "episodic" in result.normalized_data
        assert len(result.normalized_data["episodic"]) == 1

        entry = result.normalized_data["episodic"][0]
        assert "My Research" in entry["content"]
        assert entry["event_type"] == "chatgpt_conversation"
        assert entry["metadata"]["external_source"] == "chatgpt"
        assert entry["metadata"]["external_id"] == "conv-abc"

    def test_multiple_conversations(self) -> None:
        convs = [
            _make_conversation(conv_id="c1", title="Chat 1"),
            _make_conversation(conv_id="c2", title="Chat 2"),
            _make_conversation(conv_id="c3", title="Chat 3"),
        ]
        result = dry_run_chatgpt({"conversations": convs})

        assert result.summary.total_items == 3
        assert result.summary.mapped_items == 3
        assert len(result.normalized_data["episodic"]) == 3

    def test_empty_conversations_list(self) -> None:
        result = dry_run_chatgpt({"conversations": []})
        assert result.summary.total_items == 0
        assert result.summary.status == "missing"
        assert "chatgpt_no_conversations" in result.warnings

    def test_missing_conversations_key(self) -> None:
        result = dry_run_chatgpt({"data": {}})
        assert result.summary.total_items == 0

    def test_content_includes_message_preview(self) -> None:
        conv = _make_conversation(messages=[("user", "What is Python?"), ("assistant", "A programming language")])
        result = dry_run_chatgpt({"conversations": [conv]})

        entry = result.normalized_data["episodic"][0]
        assert "user: What is Python?" in entry["content"]
        assert "assistant: A programming language" in entry["content"]

    def test_long_messages_truncated(self) -> None:
        long_msg = "x" * 500
        conv = _make_conversation(messages=[("user", long_msg)])
        result = dry_run_chatgpt({"conversations": [conv]})

        entry = result.normalized_data["episodic"][0]
        assert len(entry["content"]) < 500

    def test_timestamp_from_create_time(self) -> None:
        conv = _make_conversation(create_time=1700000000.0)
        result = dry_run_chatgpt({"conversations": [conv]})

        entry = result.normalized_data["episodic"][0]
        assert "2023-11" in entry["timestamp"]

    def test_conversation_id_in_metadata(self) -> None:
        conv = _make_conversation(conv_id="unique-id-123")
        result = dry_run_chatgpt({"conversations": [conv]})

        entry = result.normalized_data["episodic"][0]
        assert entry["metadata"]["external_id"] == "unique-id-123"


class TestAutoDetectionIntegration:
    """Integration with the main adapter dispatcher."""

    def test_auto_detect_chatgpt_from_structure(self) -> None:
        conv = _make_conversation()
        result = build_memory_import_dry_run({"conversations": [conv]})
        assert result.summary.source == "chatgpt"

    def test_explicit_source_tag(self) -> None:
        conv = _make_conversation()
        result = build_memory_import_dry_run({"_source": "chatgpt", "conversations": [conv]})
        assert result.summary.source == "chatgpt"

    def test_explicit_source_param(self) -> None:
        conv = _make_conversation()
        result = build_memory_import_dry_run({"conversations": [conv]}, source="chatgpt")
        assert result.summary.source == "chatgpt"
