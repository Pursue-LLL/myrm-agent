"""Unit tests for chat_memory_events: memory influence ledger projection helpers.

Covers the pure normalization helpers (``_optional_str`` / ``_optional_float`` /
``_dict_int`` / ``_trace_steps`` / ``_memory_influence_refs``) and the
``record_memory_influence_event`` orchestration with mocked ledger + session.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.chat.chat_memory_events import (
    _dict_int,
    _memory_influence_refs,
    _optional_float,
    _optional_str,
    _trace_steps,
    record_memory_influence_event,
)


def test_optional_str() -> None:
    assert _optional_str("abc") == "abc"
    assert _optional_str("") is None
    assert _optional_str(42) is None
    assert _optional_str(None) is None


def test_optional_float() -> None:
    assert _optional_float(True) is None
    assert _optional_float(False) is None
    assert _optional_float(3) == 3.0
    assert _optional_float(2.5) == 2.5
    assert _optional_float("x") is None
    assert _optional_float(None) is None


def test_dict_int() -> None:
    assert _dict_int(None, "k") == 0
    assert _dict_int({"k": True}, "k") == 0
    assert _dict_int({"k": 5}, "k") == 5
    assert _dict_int({"k": -3}, "k") == 0
    assert _dict_int({"k": 2.7}, "k") == 2
    assert _dict_int({"k": "x"}, "k") == 0
    assert _dict_int({"k": 2}, "missing") == 0


def test_trace_steps_guards() -> None:
    assert _trace_steps({}) == []
    assert _trace_steps({"steps": "oops"}) == []
    assert _trace_steps({"steps": 7}) == []


def test_trace_steps_filters_non_dict_and_normalizes_keys() -> None:
    assert _trace_steps({"steps": [{"phase": "recall", 1: "ignored"}, "junk", None]}) == [{"phase": "recall"}]


def test_memory_influence_refs_guards() -> None:
    assert _memory_influence_refs({}) == []
    assert _memory_influence_refs({"citedMemoryRefs": "oops"}) == []
    assert _memory_influence_refs({"citedMemoryRefs": [42, "junk"]}) == []


def test_memory_influence_refs_requires_str_id_and_type() -> None:
    assert _memory_influence_refs({"citedMemoryRefs": [{"id": 1, "memory_type": "x"}]}) == []
    assert _memory_influence_refs({"citedMemoryRefs": [{"id": "m1", "memory_type": 7}]}) == []


def test_memory_influence_refs_full_projection() -> None:
    refs = _memory_influence_refs(
        {
            "citedMemoryRefs": [
                {
                    "id": "m1",
                    "memory_type": "episodic",
                    "score": 0.9,
                    "content": "content-preview",
                    "primary_namespace": "ns-a",
                    "namespaces": ["ns-a", 3, None],
                    "source_chat_id": "chat-1",
                    "source_message_id": "msg-1",
                },
                {
                    "id": "m2",
                    "memory_type": "semantic",
                    "namespaces": "not-a-list",
                },
            ]
        }
    )
    assert len(refs) == 2
    first = refs[0]
    assert first.memory_id == "m1"
    assert first.memory_type == "episodic"
    assert first.score == 0.9
    assert first.content_preview == "content-preview"
    assert first.primary_namespace == "ns-a"
    assert first.namespaces == ["ns-a"]
    assert first.source_chat_id == "chat-1"
    assert first.source_message_id == "msg-1"
    assert first.reason == "memory_search_tool"
    assert refs[1].namespaces == []


@pytest.mark.asyncio
async def test_record_event_noop_without_extra_data() -> None:
    with (
        patch("app.database.connection.get_session") as mock_gs,
        patch("app.services.memory.operation_ledger.MemoryOperationLedgerService") as mock_ledger_cls,
    ):
        await record_memory_influence_event(
            chat_id="chat-x",
            message_id="msg-x",
            content="",
            extra_data=None,
        )
        await record_memory_influence_event(
            chat_id="chat-x",
            message_id="msg-x",
            content="",
            extra_data={},
        )
        await record_memory_influence_event(
            chat_id="chat-x",
            message_id="msg-x",
            content="",
            extra_data={"other": "field"},
        )
    mock_gs.assert_not_called()
    mock_ledger_cls.assert_not_called()


def _traces_extra_data() -> dict[str, object]:
    return {
        "memoryRetrievalTraces": [
            {
                "id": "t1",
                "query_preview": "some query",
                "result_count": 2,
                "steps": [
                    {"phase": "recall", "status": "skipped", "summary": "skip", "output_count": 0},
                    {"phase": "refine", "status": "warning", "title": "title-two", "output_count": 3},
                    {"phase": "verify", "status": "error", "output_count": 1, "duration_ms": 12.5},
                    {"phase": "done", "status": "other", "output_count": 4},
                ],
            }
        ]
    }


@pytest.mark.asyncio
async def test_record_event_projects_recall_traces() -> None:
    mock_db = AsyncMock()
    mock_ledger = AsyncMock()
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = mock_db
    with (
        patch("app.database.connection.get_session", return_value=session_cm),
        patch(
            "app.services.memory.operation_ledger.MemoryOperationLedgerService",
            return_value=mock_ledger,
        ) as mock_ledger_cls,
    ):
        await record_memory_influence_event(
            chat_id="chat-x",
            message_id="msg-x",
            content="answer",
            extra_data=_traces_extra_data(),
        )

    mock_ledger_cls.assert_called_once_with(mock_db)
    assert mock_ledger.record_event.await_count == 4
    statuses = [call.kwargs["status"].name for call in mock_ledger.record_event.call_args_list]
    assert statuses == ["SKIPPED", "WARNING", "ERROR", "SUCCESS"]
    for call in mock_ledger.record_event.call_args_list:
        assert call.kwargs["kind"].name == "RECALL"
        assert call.kwargs["target_id"] == "chat-x"
        assert call.kwargs["correlation_id"] == "msg-x"
        assert call.kwargs["metadata"]["trace_id"] == "t1"
        assert call.kwargs["metadata"]["query_preview"] == "some query"
    first_call = mock_ledger.record_event.call_args_list[0].kwargs
    assert first_call["metadata"]["step_index"] == 0
    assert first_call["metadata"]["step_phase"] == "recall"
    assert first_call["summary"] == "skip"
    last_call = mock_ledger.record_event.call_args_list[3].kwargs
    assert last_call["metadata"]["step_index"] == 3
    assert last_call["metadata"]["duration_ms"] is None
    assert last_call["metadata"]["result_count"] == 2
    verify_call = mock_ledger.record_event.call_args_list[2].kwargs
    assert verify_call["metadata"]["duration_ms"] == 12.5
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_event_projects_cite_refs() -> None:
    mock_db = AsyncMock()
    mock_ledger = AsyncMock()
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = mock_db
    extra = {"citedMemoryRefs": [{"id": "m1", "memory_type": "episodic", "score": 0.8}]}
    with (
        patch("app.database.connection.get_session", return_value=session_cm),
        patch(
            "app.services.memory.operation_ledger.MemoryOperationLedgerService",
            return_value=mock_ledger,
        ),
    ):
        await record_memory_influence_event(
            chat_id="chat-x",
            message_id="msg-x",
            content="answer used memories",
            extra_data=extra,
        )

    cite_calls = [c for c in mock_ledger.record_event.call_args_list if c.kwargs["kind"].name == "CITE"]
    assert len(cite_calls) == 1
    assert cite_calls[0].kwargs["influence_refs"][0].memory_id == "m1"
    assert cite_calls[0].kwargs["metadata"]["influence_count"] == 1
    assert "answer used memories" in cite_calls[0].kwargs["summary"]
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_event_swallows_ledger_errors() -> None:
    mock_db = AsyncMock()
    mock_ledger = AsyncMock()
    mock_ledger.record_event.side_effect = RuntimeError("ledger down")
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = mock_db
    with (
        patch("app.database.connection.get_session", return_value=session_cm),
        patch(
            "app.services.memory.operation_ledger.MemoryOperationLedgerService",
            return_value=mock_ledger,
        ),
    ):
        await record_memory_influence_event(
            chat_id="chat-x",
            message_id="msg-x",
            content="answer",
            extra_data=_traces_extra_data(),
        )
    assert mock_ledger.record_event.await_count >= 1
