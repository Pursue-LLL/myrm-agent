"""What the collector keeps of each kind of event that ends or shapes a turn: why it stopped, usage, council phases."""

from __future__ import annotations

from app.services.agent.streaming_support.stream_collector import StreamContentCollector


def _saved(collector: StreamContentCollector) -> dict[str, object]:
    return collector.extra_data or {}


def test_an_engine_limit_is_saved_as_the_reason_the_turn_stopped() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "engine_limit_reached", "data": {"message": "  Budget spent  ", "limit": 5}})

    assert _saved(collector)["stopReason"] == {
        "code": "engine_limit_reached",
        "category": "limit",
        "message": "Budget spent",
        "detail": {"message": "  Budget spent  ", "limit": 5},
    }


def test_an_engine_limit_without_detail_gets_the_default_message() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "engine_limit_reached"})

    assert _saved(collector)["stopReason"] == {
        "code": "engine_limit_reached",
        "category": "limit",
        "message": "Engine limit reached",
    }


def test_an_error_event_is_saved_with_its_message_and_type() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "error", "error": " model unreachable ", "error_type": "ConnectError"})

    assert _saved(collector)["stopReason"] == {
        "code": "error",
        "category": "error",
        "message": "model unreachable",
        "detail": {"error_type": "ConnectError"},
    }


def test_an_error_event_may_carry_its_message_as_data() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "error", "data": "  tool crashed "})

    assert _saved(collector)["stopReason"] == {"code": "error", "category": "error", "message": "tool crashed"}


def test_an_error_event_without_a_message_saves_no_stop_reason() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "error", "error": "   ", "data": ""})

    assert "stopReason" not in _saved(collector)


def test_a_limit_is_not_replaced_by_an_error_that_follows_it() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "engine_limit_reached", "data": {"message": "Budget spent"}})
    collector.feed_event({"type": "error", "error": "late failure"})

    stop_reason = _saved(collector)["stopReason"]
    assert isinstance(stop_reason, dict)
    assert stop_reason["code"] == "engine_limit_reached"


def test_council_phases_are_saved_in_the_order_they_arrive() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "council_phase", "data": {"phase": "draft", "index": 1}})
    collector.feed_event({"type": "council_phase", "data": "not a phase"})
    collector.feed_event({"type": "council_phase", "data": {"phase": "vote", "index": 2}})

    assert _saved(collector)["councilPhases"] == [{"phase": "draft", "index": 1}, {"phase": "vote", "index": 2}]


def test_token_usage_is_saved_as_the_turns_usage() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "token_usage", "data": {"usage": {"input_tokens": 12, "output_tokens": 3}}})

    assert _saved(collector)["usage"] == {"input_tokens": 12, "output_tokens": 3}


def test_token_usage_that_is_not_an_object_is_ignored() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "token_usage", "data": "12 tokens"})
    collector.feed_event({"type": "token_usage", "data": ["usage"]})

    assert "usage" not in _saved(collector)
