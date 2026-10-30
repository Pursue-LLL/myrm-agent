"""The edges of what the collector keeps: the exact limits, blank or mistyped fields, and what each kind of output alone counts for."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from app.services.agent.streaming_support.stream_collector import (
    _MAX_REASONING_CHARS,
    ACTIVE_COLLECTORS,
    StreamContentCollector,
)

CHAT_ID = "chat-collector-boundaries"


@pytest.fixture(autouse=True)
def _release_collector() -> Iterator[None]:
    yield
    ACTIVE_COLLECTORS.pop(CHAT_ID, None)


def _saved(collector: StreamContentCollector) -> dict[str, object]:
    return collector.extra_data or {}


def _step_event(step_key: str, tool_call_id: str) -> dict[str, object]:
    return {"type": "tasks_steps", "step_key": step_key, "tool_call_id": tool_call_id, "data": []}


def test_the_first_message_id_seen_is_kept_and_blank_or_mistyped_ids_are_ignored() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "message", "data": "a", "messageId": ""})
    collector.feed_event({"type": "message", "data": "b", "messageId": 7})
    assert collector.message_id is None

    collector.feed_event({"type": "message", "data": "c", "messageId": "m1"})
    collector.feed_event({"type": "message", "data": "d", "messageId": "m2"})
    assert collector.message_id == "m1"


def test_a_small_reasoning_chunk_is_kept_whole_and_not_marked_truncated() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "reasoning", "data": "short thought"})

    saved = _saved(collector)
    assert saved["reasoning"] == "short thought"
    assert "reasoningTruncated" not in saved


def test_reasoning_that_exactly_fills_the_limit_is_not_marked_truncated() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "reasoning", "data": "x" * _MAX_REASONING_CHARS})

    saved = _saved(collector)
    assert saved["reasoning"] == "x" * _MAX_REASONING_CHARS
    assert "reasoningTruncated" not in saved


def test_reasoning_beyond_the_limit_is_cut_at_the_limit_and_marked() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "reasoning", "data": "x" * (_MAX_REASONING_CHARS + 1)})

    saved = _saved(collector)
    assert saved["reasoning"] == "x" * _MAX_REASONING_CHARS
    assert saved["reasoningTruncated"] is True
    assert saved["reasoningCharLimit"] == _MAX_REASONING_CHARS


def test_tool_steps_reach_the_run_digest_only_for_a_chat() -> None:
    with patch("app.services.copilot.run_digest_store.RunDigestStore.update_from_progress", new=MagicMock()) as update:
        StreamContentCollector().feed_event(_step_event("web_search", "c1"))
        update.assert_not_called()

        StreamContentCollector(chat_id=CHAT_ID).feed_event(_step_event("web_search", "c1"))
        update.assert_called_once()
        assert update.call_args.args[0] == CHAT_ID


def test_an_iteration_limit_is_saved_with_its_detail_and_a_message_that_names_it() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "iteration_limit_reached", "data": {"limit": 50, "nodes_completed": 50}})

    assert _saved(collector)["stopReason"] == {
        "code": "iteration_limit_reached",
        "category": "limit",
        "message": "Iteration limit reached (50 iterations / 50 nodes)",
        "detail": {"limit": 50, "nodes_completed": 50},
    }


def test_an_iteration_limit_without_a_detail_object_is_saved_with_the_default_message_only() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "iteration_limit_reached", "data": "50"})

    assert _saved(collector)["stopReason"] == {
        "code": "iteration_limit_reached",
        "category": "limit",
        "message": "Iteration limit reached",
    }


@pytest.mark.parametrize("message", ["   ", 5, None])
def test_an_engine_limit_whose_message_is_blank_or_not_text_gets_the_default_message(message: object) -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "engine_limit_reached", "data": {"message": message}})

    stop_reason = _saved(collector)["stopReason"]
    assert isinstance(stop_reason, dict)
    assert stop_reason["message"] == "Engine limit reached"


def test_an_error_event_with_only_text_data_is_saved_with_that_text() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "error", "data": "  boom  "})

    stop_reason = _saved(collector)["stopReason"]
    assert isinstance(stop_reason, dict)
    assert stop_reason["message"] == "boom"


@pytest.mark.parametrize("data", [None, "   ", {"detail": "x"}, 5])
def test_an_error_event_with_no_text_to_show_is_not_a_stop_reason(data: object) -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "error", "data": data})

    assert "stopReason" not in _saved(collector)


@pytest.mark.parametrize("skills", [5, "abc", [], ["not-an-object"]])
def test_turn_loaded_skills_that_are_not_a_list_of_objects_are_not_saved(skills: object) -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "message_end", "turn_loaded_skills": skills})

    assert "turnLoadedSkills" not in _saved(collector)


@pytest.mark.parametrize(
    ("ttft", "saved"),
    [(0, 0), (12.7, 12), (-1, None), ("12", None)],
)
def test_a_first_token_time_is_saved_when_it_is_a_number_of_zero_or_more(ttft: object, saved: int | None) -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "message_end", "stream_ttft_ms": ttft})

    assert _saved(collector).get("streamTtftMs") == saved


def test_each_cited_memory_id_is_saved_once_and_only_when_it_is_text() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "message_end", "cited_memory_ids": ["a", "a", 5, "b"]})

    assert _saved(collector)["citedMemoryIds"] == ["a", "b"]


def test_a_cache_break_is_saved_only_from_the_cache_break_step_and_only_with_an_object() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "status", "step_key": "thinking", "data": {"reason": "ignored"}})
    collector.feed_event({"type": "status", "step_key": "cache_break", "data": "not-an-object"})
    assert "cacheBreak" not in _saved(collector)

    collector.feed_event({"type": "status", "step_key": "cache_break", "data": {"reason": "prompt changed"}})
    assert _saved(collector)["cacheBreak"] == {"reason": "prompt changed"}


def test_a_failover_status_is_saved_as_a_step_named_after_its_error_kind_and_fallback_model() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "status", "step_key": "model_failover", "error_kind": "rate_limit", "fallback_model": "gpt-x"})

    assert _saved(collector)["progressSteps"] == [
        {"step_key": "model_failover_rate_limit", "items": [{"text": "gpt-x"}], "status": "success"}
    ]


@pytest.mark.parametrize("error_kind", [None, "", 5])
def test_a_failover_status_without_a_usable_error_kind_keeps_the_plain_step_name(error_kind: object) -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "status", "step_key": "model_failover", "error_kind": error_kind})

    assert _saved(collector)["progressSteps"] == [{"step_key": "model_failover", "items": [], "status": "success"}]


def test_a_collector_has_active_generation_only_once_it_holds_output_of_some_kind() -> None:
    assert StreamContentCollector().has_active_generation is False

    with_text = StreamContentCollector()
    with_text.feed_event({"type": "message", "data": "hello"})
    assert with_text.has_active_generation is True

    with_step = StreamContentCollector()
    with_step.feed_event(_step_event("web_search", "c1"))
    assert with_step.has_content is False
    assert with_step.has_active_generation is True

    with_card = StreamContentCollector()
    with_card.feed_event({"type": "clarification_required", "data": {"question": "which one?"}})
    assert with_card.has_content is False
    assert with_card.has_active_generation is True


def test_a_citation_audit_is_saved_only_when_the_answer_cites_a_source() -> None:
    collector = StreamContentCollector()
    collector.feed_event({"type": "sources", "data": [{"url": "https://a.test", "title": "one"}]})
    collector.feed_event({"type": "message", "data": "An answer without citations."})
    assert "citationAudit" not in _saved(collector)

    cited = StreamContentCollector()
    cited.feed_event({"type": "sources", "data": [{"url": "https://a.test", "title": "one"}]})
    cited.feed_event({"type": "message", "data": "It cites \u30101\u3011 and a source that does not exist \u30109\u3011."})
    assert _saved(cited)["citationAudit"] == {"totalMarkers": 2, "valid": 1, "unresolved": 1}


def test_a_memory_retrieval_trace_needs_a_text_id_and_is_saved_once() -> None:
    collector = StreamContentCollector()
    for trace in ({"id": 5}, {"id": ""}, {"id": "t1", "query": "q"}, {"id": "t1", "query": "again"}):
        collector.feed_event({"type": "tool_end", "tool_name": "memory_search", "memory_retrieval_trace": trace})

    assert _saved(collector)["memoryRetrievalTraces"] == [{"id": "t1", "query": "q"}]
