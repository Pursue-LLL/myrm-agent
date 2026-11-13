"""Unit tests for ResultFormatter formatting (gutter, per-line clamp, BOM)."""

from myrm_agent_harness.agent.meta_tools.file_ops.core.operation_context import ViewRange
from myrm_agent_harness.agent.meta_tools.file_ops.core.result_formatter import (
    FileContent,
    ResultFormatter,
)


def _format(lines: list[str], **kwargs) -> str:
    content = FileContent(
        path=kwargs.get("path", "/tmp/f.py"),
        display_path=kwargs.get("display_path", "f.py"),
        lines=lines,
        view_range=kwargs.get("view_range"),
    )
    return ResultFormatter.format_file_content(
        content,
        max_line_length=kwargs.get("max_line_length"),
    )


def test_format_no_view_range_adds_gutter():
    result = _format(["a", "b"])
    assert "1|a" in result
    assert "2|b" in result


def test_format_view_range_slices_lines():
    lines = [f"line{i}" for i in range(1, 11)]
    result = _format(lines, view_range=ViewRange(start=3, end=5), path="/tmp/f.py", display_path="f.py")
    assert "3|line3" in result
    assert "4|line4" in result
    assert "5|line5" in result
    assert "line1" not in result
    assert "lines 3-5 of 10" in result


def test_format_view_range_to_end():
    lines = [f"line{i}" for i in range(1, 6)]
    result = _format(lines, view_range=ViewRange(start=4, end=-1), path="/tmp/f.py", display_path="f.py")
    assert "4|line4" in result
    assert "5|line5" in result


def test_format_clamps_long_line():
    result = _format(["a" * 100, "short"], max_line_length=10, path="/tmp/f.py", display_path="f.py")
    assert f"{'a' * 10}... [truncated]" in result
    assert "2|short" in result


def test_format_clamps_long_line_in_view_range():
    lines = ["x" * 100, "y"]
    result = _format(
        lines, max_line_length=5, view_range=ViewRange(start=1, end=2), path="/tmp/f.py", display_path="f.py"
    )
    assert f"{'x' * 5}... [truncated]" in result


def test_format_no_clamp_when_none():
    result = _format(["a" * 100], max_line_length=None, path="/tmp/f.py", display_path="f.py")
    assert "a" * 100 in result


def test_format_strips_utf8_bom_on_first_line():
    result = _format(["\ufeffhello", "world"], path="/tmp/f.py", display_path="f.py")
    assert "1|hello" in result
    assert "\ufeff" not in result
    assert "2|world" in result


def test_format_strips_bom_in_view_range_first_line():
    result = _format(
        ["\ufeffa", "b", "c"],
        view_range=ViewRange(start=1, end=2),
        path="/tmp/f.py",
        display_path="f.py",
    )
    assert "1|a" in result
    assert "\ufeff" not in result


def test_format_shows_plain_lines_for_a_crlf_file():
    lines = ["a\r", "b\r", "c"]

    result = _format(lines)

    assert "\r" not in result
    assert "1|a\n" in result
    assert "2|b\n" in result
    assert result.count("3|c") == 1
    assert lines == ["a\r", "b\r", "c"]


def test_format_shows_plain_lines_for_a_crlf_file_in_view_range():
    result = _format(["a\r", "b\r", "c\r", "d"], view_range=ViewRange(start=2, end=3))

    assert "\r" not in result
    assert "2|b\n" in result
    assert "3|c\n" in result


def test_format_removes_only_the_carriage_return_that_ends_a_line():
    assert "1|a\rb\n" in _format(["a\rb\r", "c"])


def test_format_clamps_a_crlf_line_by_its_text_without_the_carriage_return():
    result = _format(["x" * 10 + "\r", "y"], max_line_length=10)

    assert "truncated" not in result
    assert f"1|{'x' * 10}\n" in result
