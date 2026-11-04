"""Head+tail truncation window: where smart_truncate cuts, and the diagnostic-tail detection behind it."""

from __future__ import annotations

import random

import pytest

from myrm_agent_harness.utils.text_utils import smart_truncate
from myrm_agent_harness.utils.truncation_window import (
    TruncationWindow,
    apply_truncation_window,
    has_important_tail,
    truncation_window,
)


class TestHasImportantTail:
    @pytest.mark.parametrize(
        "text",
        [
            "Some content\n" * 50 + "ERROR: File not found",
            "Normal output\n" * 50 + "Exception occurred at line 42",
            "Code output\n" * 50 + "Traceback (most recent call last):",
            '{"data": "value"}\n' * 30 + "  }\n]",
            "Test results\n" * 50 + "Total: 100 tests passed",
            "some data\n}",
            "blah\ntotal: 42 passed",
        ],
    )
    def test_diagnostic_structural_or_summary_tail_is_important(self, text: str) -> None:
        assert has_important_tail(text) is True

    @pytest.mark.parametrize("text", ["This is normal text. " * 100, "plain text", "Short", ""])
    def test_plain_tail_is_not_important(self, text: str) -> None:
        assert has_important_tail(text) is False

    def test_only_the_last_two_thousand_chars_are_inspected(self) -> None:
        text = "ERROR: boom\n" + "calm text. " * 400
        assert has_important_tail(text) is False


class TestTruncationWindow:
    def test_text_within_budget_has_no_window(self) -> None:
        assert truncation_window("short", 100) is None
        assert truncation_window("x" * 100, 100) is None

    def test_one_char_over_budget_gets_a_window(self) -> None:
        assert truncation_window("x" * 101, 100) is not None

    def test_cuts_snap_to_line_boundaries_when_a_newline_is_close(self) -> None:
        text = "line\n" * 400
        window = truncation_window(text, 500)

        assert window is not None
        assert text[window.head_end] == "\n"
        assert text[window.tail_start - 1] == "\n"

    def test_cuts_stay_mid_line_when_no_newline_is_close(self) -> None:
        text = "x" * 5000
        window = truncation_window(text, 500)

        assert window is not None
        assert text[window.head_end] != "\n"
        assert window.head_end < window.tail_start

    def test_diagnostic_tail_shifts_the_budget_toward_the_tail(self) -> None:
        calm = "Line\n" * 400
        alarming = calm + "ERROR: Critical failure\n"

        calm_window = truncation_window(calm, 500)
        alarming_window = truncation_window(alarming, 500)

        assert calm_window is not None and alarming_window is not None
        assert len(alarming) - alarming_window.tail_start > len(calm) - calm_window.tail_start

    def test_tail_ratio_moves_the_tail_start(self) -> None:
        text = "Content\n" * 400
        small = truncation_window(text, 500, tail_ratio=0.2)
        large = truncation_window(text, 500, tail_ratio=0.5)

        assert small is not None and large is not None
        assert large.tail_start < small.tail_start

    def test_budget_floor_can_make_the_window_overlap(self) -> None:
        """A tiny budget is floored to 200 chars, which can exceed the text itself; callers see it as 'nothing to omit'."""
        window = truncation_window("x" * 150, 100)

        assert window == TruncationWindow(head_end=140, tail_start=90)
        assert window.head_end >= window.tail_start

    def test_window_never_overlaps_once_the_budget_exceeds_the_floor(self) -> None:
        rng = random.Random(7)
        for _ in range(300):
            text = "".join(rng.choice(["alpha ", "beta\n", "x", "\n\n", "error "]) for _ in range(rng.randint(60, 900)))
            max_chars = rng.randint(500, max(500, len(text) - 1))
            window = truncation_window(text, max_chars)
            if window is not None:
                assert window.head_end < window.tail_start


class TestApplyTruncationWindow:
    def test_marker_states_how_much_of_each_end_is_kept(self) -> None:
        text = "line\n" * 400
        window = truncation_window(text, 500)
        assert window is not None

        result = apply_truncation_window(text, window)

        head = text[: window.head_end]
        tail = text[window.tail_start :]
        assert result == f"{head}\n\n[Truncated: {len(text)} chars -> first {len(head)} + last {len(tail)}]\n\n{tail}"

    @pytest.mark.parametrize("max_chars", [150, 300, 500, 2000])
    def test_matches_smart_truncate(self, max_chars: int) -> None:
        text = ("alpha beta\n" * 80) + "x" * 600 + "\nTotal: 3 passed\n"
        window = truncation_window(text, max_chars)

        expected = text if window is None else apply_truncation_window(text, window)
        assert smart_truncate(text, max_chars) == expected

    def test_smart_truncate_returns_the_text_untouched_when_it_fits(self) -> None:
        assert smart_truncate("short text", 100) == "short text"
