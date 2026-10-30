"""What the collector saves about a turn, so the chat looks the same when it is opened again."""

from __future__ import annotations

from app.services.agent.streaming_support.stream_collector import StreamContentCollector


def _saved(collector: StreamContentCollector) -> dict[str, object]:
    return collector.extra_data or {}


def _step_keys(steps: object) -> list[object]:
    assert isinstance(steps, list)
    return [step["step_key"] for step in steps if isinstance(step, dict)]


def test_archive_restore_steps_are_saved_with_their_block_and_result() -> None:
    collector = StreamContentCollector()

    collector.feed_event(
        {
            "type": "status",
            "step_key": "archive_restore_blocked",
            "tool_name": "read_file",
            "items": [{"text": "x"}],
            "status": "blocked",
            "data": {"archive_restore_block": {"path": "a.zip"}},
        }
    )
    collector.feed_event(
        {
            "type": "status",
            "step_key": "archive_restore_result",
            "status": "success",
            "data": {"archive_restore_result": {"restored": 2}},
        }
    )

    steps = _saved(collector)["progressSteps"]
    assert isinstance(steps, list)
    blocked, result = steps
    assert blocked["step_key"] == "archive_restore_blocked"
    assert blocked["items"] == [{"text": "x"}]
    assert blocked["archive_restore_block"] == {"path": "a.zip"}
    assert "archive_restore_result" not in blocked
    assert result["step_key"] == "archive_restore_result"
    assert result["archive_restore_result"] == {"restored": 2}
    assert "archive_restore_block" not in result


def test_a_status_step_that_is_not_about_archive_restore_is_not_saved() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "status", "step_key": "thinking", "status": "running"})

    assert collector.extra_data is None


def test_a_resolved_plan_confirmation_keeps_the_plan_it_resolved() -> None:
    collector = StreamContentCollector()

    collector.feed_event(
        {"type": "status", "data": {"phase": "plan_confirm", "status": "waiting", "plan": "do it", "spawn_count": 2}}
    )
    collector.feed_event({"type": "status", "data": {"phase": "plan_confirm", "status": "resolved", "modified": True}})

    assert _saved(collector)["planConfirmation"] == {
        "plan": "do it",
        "status": "edited",
        "source": "deep_research",
        "spawnCount": 2,
    }


def test_the_routing_choice_and_its_reason_are_saved() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "routing_decision", "data": {"tier": "fast", "reason": "short question"}})

    saved = _saved(collector)
    assert saved["routingTier"] == "fast"
    assert saved["routingReason"] == "short question"


def test_a_routing_choice_that_is_not_a_mapping_is_ignored() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "routing_decision", "data": "fast"})

    assert collector.extra_data is None


def test_the_skills_loaded_for_a_turn_are_saved_when_the_turn_ends() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "message_end", "turn_loaded_skills": [{"name": "report"}, "junk"]})

    assert _saved(collector)["turnLoadedSkills"] == [{"name": "report"}]


def test_a_snapshot_lists_the_steps_in_order_and_each_source_once() -> None:
    collector = StreamContentCollector()
    collector.feed_event({"type": "tasks_steps", "step_key": "web_search", "tool_call_id": "c1", "data": []})
    collector.feed_event({"type": "tasks_steps", "step_key": "read_file", "tool_call_id": "c2", "data": []})
    collector.feed_event({"type": "sources", "data": [{"url": "https://a.test", "title": "one"}]})
    collector.feed_event({"type": "sources", "data": [{"url": "https://a.test", "title": "two"}, {"url": "https://b.test"}]})

    snapshot = collector.get_snapshot()

    assert _step_keys(snapshot["progress_steps"]) == ["web_search", "read_file"]
    assert snapshot["sources"] == [{"url": "https://a.test", "title": "two"}, {"url": "https://b.test"}]


def test_a_stream_that_dies_without_ending_is_saved_as_errored() -> None:
    collector = StreamContentCollector()

    collector.mark_stream_completion_error()

    assert _saved(collector)["completionStatus"] == "error"
