"""CacheBreakDetector message-prefix tracking: which earlier message of the request changed between two calls."""

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from myrm_agent_harness.agent.context_management.infra.cache_break_detector import CacheBreakDetector


class TestMessagePrefix:
    @pytest.fixture()
    def detector(self) -> CacheBreakDetector:
        return CacheBreakDetector()

    @pytest.fixture()
    def msgs(self) -> list[HumanMessage]:
        return [HumanMessage(content="Hi")]

    def test_the_first_request_has_nothing_to_differ_from(self, detector: CacheBreakDetector) -> None:
        detector.record_message_prefix(("a", "b"))

        assert detector.consume_prefix_shift() is None

    def test_a_request_that_only_appends_leaves_no_shift(self, detector: CacheBreakDetector) -> None:
        detector.record_message_prefix(("a", "b"))
        detector.record_message_prefix(("a", "b", "c"))

        assert detector.consume_prefix_shift() is None

    def test_an_edited_message_is_handed_out_once(self, detector: CacheBreakDetector) -> None:
        detector.record_message_prefix(("a", "b"))
        detector.record_message_prefix(("a", "x", "c"))

        shift = detector.consume_prefix_shift()

        assert shift is not None
        assert (shift.first_index, shift.previous_length, shift.current_length) == (1, 2, 3)
        assert not shift.announced
        assert detector.consume_prefix_shift() is None

    def test_a_request_that_appends_again_does_not_inherit_the_earlier_shift(
        self, detector: CacheBreakDetector
    ) -> None:
        detector.record_message_prefix(("a", "b"))
        detector.record_message_prefix(("a", "x"))
        detector.record_message_prefix(("a", "x", "c"))

        assert detector.consume_prefix_shift() is None

    def test_a_cache_break_names_the_edited_message(
        self, detector: CacheBreakDetector, msgs: list[HumanMessage]
    ) -> None:
        detector.record_prompt_state(msgs, "m")
        detector.record_message_prefix(("a", "b", "c"))
        detector.check_cache_break(10_000)
        detector.record_prompt_state(msgs, "m")
        detector.record_message_prefix(("a", "x", "c"))

        event = detector.check_cache_break(2_000)

        assert event is not None
        assert event.reasons == ("message 1 rewritten (3 → 3 messages)",)
        assert any("byte-identical" in action for action in event.suggested_actions)

    def test_a_cache_break_names_a_truncated_history(
        self, detector: CacheBreakDetector, msgs: list[HumanMessage]
    ) -> None:
        detector.record_prompt_state(msgs, "m")
        detector.record_message_prefix(("a", "b", "c"))
        detector.check_cache_break(10_000)
        detector.record_prompt_state(msgs, "m")
        detector.record_message_prefix(("a", "b"))

        event = detector.check_cache_break(2_000)

        assert event is not None
        assert event.reasons == ("history truncated (3 → 2 messages)",)

    def test_a_shift_joins_the_other_changes_of_the_same_call(self, detector: CacheBreakDetector) -> None:
        detector.record_prompt_state([SystemMessage(content="A")], "m")
        detector.record_message_prefix(("a", "b"))
        detector.check_cache_break(10_000)
        detector.record_prompt_state([SystemMessage(content="B")], "m")
        detector.record_message_prefix(("a", "x"))

        event = detector.check_cache_break(2_000)

        assert event is not None
        assert "system prompt changed" in event.reasons
        assert "message 1 rewritten (2 → 2 messages)" in event.reasons

    def test_a_shift_alone_replaces_the_guess_about_ttl_or_the_server(
        self, detector: CacheBreakDetector, msgs: list[HumanMessage]
    ) -> None:
        detector.record_prompt_state(msgs, "m")
        detector.record_message_prefix(("a", "b"))
        detector.check_cache_break(10_000)
        detector.record_prompt_state(msgs, "m")
        detector.record_message_prefix(("a", "x"))

        event = detector.check_cache_break(2_000)

        assert event is not None
        assert not any("TTL" in reason or "server-side" in reason for reason in event.reasons)

    def test_a_rewrite_the_pipeline_announced_is_flagged_and_is_no_break(
        self, detector: CacheBreakDetector, msgs: list[HumanMessage]
    ) -> None:
        detector.record_prompt_state(msgs, "m")
        detector.record_message_prefix(("a", "b"))
        detector.check_cache_break(10_000)
        detector.notify_compaction()
        detector.record_prompt_state(msgs, "m")
        detector.record_message_prefix(("summary",))

        shift = detector.consume_prefix_shift()

        assert shift is not None
        assert shift.announced
        assert detector.check_cache_break(0) is None

    def test_the_call_after_an_announced_rewrite_is_judged_by_its_own_prefix(
        self, detector: CacheBreakDetector, msgs: list[HumanMessage]
    ) -> None:
        detector.record_prompt_state(msgs, "m")
        detector.record_message_prefix(("a", "b"))
        detector.check_cache_break(10_000)
        detector.notify_compaction()
        detector.record_message_prefix(("summary",))
        detector.check_cache_break(0)
        detector.record_message_prefix(("summary", "next"))

        assert detector.consume_prefix_shift() is None
