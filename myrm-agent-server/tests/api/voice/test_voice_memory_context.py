"""Unit tests for voice memory ACL SSOT."""

from __future__ import annotations

from app.api.voice.tool_catalog import (
    build_memory_search_tool_parameters,
    memory_search_corpus_enum,
)
from app.api.voice.voice_memory_context import VoiceMemoryContext, voice_memory_context_from


def test_voice_memory_context_from_respects_settings_and_profile() -> None:
    ctx = voice_memory_context_from(
        {"enableMemory": True, "memoryEnableConversationSearch": True},
        ("memory", "wiki"),
    )
    assert ctx.enable_memory is True
    assert ctx.enable_conversation_search is True
    assert ctx.enable_wiki is True


def test_voice_memory_context_sessions_requires_memory_on() -> None:
    ctx = voice_memory_context_from(
        {"enableMemory": False, "memoryEnableConversationSearch": True},
        ("memory",),
    )
    assert ctx.enable_memory is False
    assert ctx.enable_conversation_search is False


def test_memory_search_corpus_enum_trims_disabled_corpora() -> None:
    ctx = VoiceMemoryContext(enable_memory=True, enable_conversation_search=False, enable_wiki=False)
    assert memory_search_corpus_enum(ctx) == ["memory"]
    params = build_memory_search_tool_parameters(memory_search_corpus_enum(ctx))
    assert "corpus" not in params["properties"]


def test_memory_search_corpus_enum_includes_sessions_when_opt_in_on() -> None:
    ctx = VoiceMemoryContext(enable_memory=True, enable_conversation_search=True, enable_wiki=True)
    enum = memory_search_corpus_enum(ctx)
    assert enum == ["memory", "wiki", "sessions", "all"]
