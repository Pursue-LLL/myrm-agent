"""Tests for line ending detection, normalization, and preservation across edits.

Covers:
- detect_line_ending: CRLF, LF, empty, single-line, mixed
- normalize_line_endings: LF→LF, LF→CRLF, CRLF→LF, CRLF→CRLF, mixed, lone CR, idempotence
- view_lines: CRLF, lone CR and LF all end a line in a view
- FileOperationService._execute_create: a new file keeps the line endings it was given
"""

from __future__ import annotations

import io
import itertools
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.utils.line_endings import (
    detect_line_ending,
    normalize_line_endings,
    view_lines,
)

# ── detect_line_ending ──────────────────────────────────────────────


class TestDetectLineEnding:
    def test_empty_string(self) -> None:
        assert detect_line_ending("") is None

    def test_no_newlines(self) -> None:
        assert detect_line_ending("single line no newline") is None

    def test_lf_only(self) -> None:
        assert detect_line_ending("line1\nline2\nline3\n") == "\n"

    def test_crlf_only(self) -> None:
        assert detect_line_ending("line1\r\nline2\r\nline3\r\n") == "\r\n"

    def test_crlf_takes_precedence_over_mixed(self) -> None:
        assert detect_line_ending("line1\r\nline2\nline3\n") == "\r\n"

    def test_large_content_scans_head_only(self) -> None:
        beyond_sample = "a" * 5000 + "\n" + "b" * 5000
        assert detect_line_ending(beyond_sample) is None

        within_sample = "a" * 3000 + "\n" + "b" * 5000
        assert detect_line_ending(within_sample) == "\n"

    def test_crlf_in_head(self) -> None:
        content = "first\r\nsecond\r\n" + "a" * 10000
        assert detect_line_ending(content) == "\r\n"

    def test_lone_cr_detected_as_none(self) -> None:
        """Lone CR (old Mac style) has no \\n so detect returns None."""
        assert detect_line_ending("line1\rline2\rline3\r") is None

    def test_crlf_at_sample_boundary_split(self) -> None:
        """CRLF split across the 4096 boundary: \\r at 4095, \\n at 4096.
        Only \\r is in head, no complete \\r\\n or \\n, so returns None."""
        content = "x" * 4095 + "\r\n" + "rest"
        assert detect_line_ending(content) is None

    def test_crlf_within_sample_boundary(self) -> None:
        """CRLF fully within sample window detects correctly."""
        content = "x" * 4094 + "\r\n" + "rest"
        assert detect_line_ending(content) == "\r\n"

    def test_crlf_just_beyond_sample(self) -> None:
        """CRLF entirely beyond the 4096 sample window."""
        content = "x" * 4097 + "\r\n"
        assert detect_line_ending(content) is None


# ── normalize_line_endings ──────────────────────────────────────────


class TestNormalizeLineEndings:
    def test_lf_to_lf(self) -> None:
        assert normalize_line_endings("a\nb\nc\n", "\n") == "a\nb\nc\n"

    def test_lf_to_crlf(self) -> None:
        assert normalize_line_endings("a\nb\nc\n", "\r\n") == "a\r\nb\r\nc\r\n"

    def test_crlf_to_lf(self) -> None:
        assert normalize_line_endings("a\r\nb\r\nc\r\n", "\n") == "a\nb\nc\n"

    def test_crlf_to_crlf(self) -> None:
        assert normalize_line_endings("a\r\nb\r\nc\r\n", "\r\n") == "a\r\nb\r\nc\r\n"

    def test_mixed_endings_to_lf(self) -> None:
        assert normalize_line_endings("a\r\nb\nc\r\n", "\n") == "a\nb\nc\n"

    def test_mixed_endings_to_crlf(self) -> None:
        assert normalize_line_endings("a\r\nb\nc\r\n", "\r\n") == "a\r\nb\r\nc\r\n"

    def test_lone_cr_to_lf(self) -> None:
        assert normalize_line_endings("a\rb\rc\r", "\n") == "a\nb\nc\n"

    def test_lone_cr_to_crlf(self) -> None:
        assert normalize_line_endings("a\rb\rc\r", "\r\n") == "a\r\nb\r\nc\r\n"

    def test_idempotent_crlf(self) -> None:
        text = "a\nb\n"
        once = normalize_line_endings(text, "\r\n")
        twice = normalize_line_endings(once, "\r\n")
        assert once == twice

    def test_idempotent_lf(self) -> None:
        text = "a\r\nb\r\n"
        once = normalize_line_endings(text, "\n")
        twice = normalize_line_endings(once, "\n")
        assert once == twice

    def test_no_newlines(self) -> None:
        assert normalize_line_endings("no newlines", "\n") == "no newlines"
        assert normalize_line_endings("no newlines", "\r\n") == "no newlines"


# ── view_lines ──────────────────────────────────────────────────────


class TestViewLines:
    """A view splits the text a file was read as; every line ending must end a line."""

    @pytest.mark.parametrize(
        ("text", "shown"),
        [
            ("a\nb\n", ["a", "b", ""]),
            ("a\r\nb\r\n", ["a", "b", ""]),
            ("a1\rb2\rc3\r", ["a1", "b2", "c3", ""]),
            ("a\rb\r\nc\n", ["a", "b", "c", ""]),
            ("x\n\r\ny", ["x", "", "y"]),
            ("abc\r\r\n", ["abc", "", ""]),
            ("no newline", ["no newline"]),
            ("", [""]),
        ],
    )
    def test_every_line_ending_ends_a_line(self, text: str, shown: list[str]) -> None:
        assert view_lines(text.split("\n")) == shown

    def test_a_text_shows_the_same_lines_with_any_line_ending(self) -> None:
        lines = ["alpha", "", "beta", "gamma"]
        shown = {ending: view_lines(ending.join(lines).split("\n")) for ending in ("\n", "\r\n", "\r")}
        assert shown["\r\n"] == shown["\r"] == shown["\n"] == lines

    def test_agrees_with_universal_newlines_for_every_short_text_over_the_line_ending_alphabet(self) -> None:
        """``preview`` and ``stream`` read through universal newlines; the view must show the lines they show."""
        for length in range(7):
            for chars in itertools.product("a\r\n", repeat=length):
                text = "".join(chars)
                expected = io.StringIO(text, newline=None).getvalue().split("\n")
                assert view_lines(text.split("\n")) == expected, repr(text)

    def test_returns_a_new_list_even_when_there_is_nothing_to_change(self) -> None:
        raw = ["a", "b"]
        shown = view_lines(raw)
        assert shown == raw
        assert shown is not raw

    def test_no_lines_shows_no_lines(self) -> None:
        assert view_lines([]) == []


# ── FileOperationService._execute_create line endings ──────────────


@pytest.mark.asyncio
async def test_create_new_file_no_normalization() -> None:
    """Creating a brand-new file should NOT alter line endings."""
    from myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service import (
        FileOperationService,
    )
    from myrm_agent_harness.agent.meta_tools.file_ops.core.operation_context import (
        OperationContext,
        OperationType,
    )

    original_text = "new content\nline2\n"
    context = OperationContext(
        operation=OperationType.CREATE,
        executor=None,
        path="brand_new.txt",
        file_text=original_text,
    )
    service = FileOperationService(context)

    mock_strategy = AsyncMock()
    mock_strategy.exists = AsyncMock(return_value=False)
    mock_strategy.read_file = AsyncMock(return_value=["new content", "line2", ""])
    mock_strategy.write_file = AsyncMock()

    with (
        patch.object(context, "validate"),
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.FileSystemStrategyFactory"
        ) as mock_factory,
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.ValidatorChain"
        ) as mock_validator,
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.check_conflict_pre_write",
            return_value=None,
        ),
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.get_file_integrity_guard",
            return_value=None,
        ),
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.validators.delta_syntax_validator.DeltaSyntaxValidator.validate"
        ),
    ):
        mock_factory.create_strategy.return_value = mock_strategy
        mock_validator.return_value.validate = AsyncMock()

        await service.execute()

    written = mock_strategy.write_file.call_args[0][1]
    assert written == original_text
    assert "\r\n" not in written
