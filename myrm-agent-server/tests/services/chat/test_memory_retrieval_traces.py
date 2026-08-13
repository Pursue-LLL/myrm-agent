"""Unit tests for chat_message._memory_retrieval_traces normalization."""

from __future__ import annotations

from app.services.chat.chat_message import _memory_retrieval_traces


def test_memory_retrieval_traces_empty_when_missing() -> None:
    assert _memory_retrieval_traces({}) == []


def test_memory_retrieval_traces_empty_when_not_list() -> None:
    assert _memory_retrieval_traces({"memoryRetrievalTraces": "oops"}) == []
    assert _memory_retrieval_traces({"memoryRetrievalTraces": 42}) == []


def test_memory_retrieval_traces_filters_non_dict_entries() -> None:
    assert _memory_retrieval_traces(
        {"memoryRetrievalTraces": [{"id": "t1", "degraded": True}, "junk", 7]}
    ) == [{"id": "t1", "degraded": True}]


def test_memory_retrieval_traces_normalizes_string_keys() -> None:
    traces = _memory_retrieval_traces(
        {
            "memoryRetrievalTraces": [
                {"id": "t1", "degraded": True, 1: "ignored"},
            ]
        }
    )
    assert traces == [{"id": "t1", "degraded": True}]
