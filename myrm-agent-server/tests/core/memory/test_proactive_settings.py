"""Unit tests for proactive memory settings resolution."""

from __future__ import annotations

from app.core.memory.proactive.settings import (
    resolve_conversation_search_enabled,
    resolve_memory_enabled,
)


def test_resolve_memory_enabled_requires_explicit_true() -> None:
    assert resolve_memory_enabled(None) is False
    assert resolve_memory_enabled({}) is False
    assert resolve_memory_enabled({"enableMemory": False}) is False
    assert resolve_memory_enabled({"enableMemory": True}) is True


def test_resolve_conversation_search_requires_memory_and_flag() -> None:
    assert resolve_conversation_search_enabled(None) is False
    assert resolve_conversation_search_enabled({"enableMemory": False, "memoryEnableConversationSearch": True}) is False
    assert resolve_conversation_search_enabled({"enableMemory": True, "memoryEnableConversationSearch": False}) is False
    assert resolve_conversation_search_enabled({"enableMemory": True, "memoryEnableConversationSearch": True}) is True
