"""Unit tests for the view of a long text the context guard parked in the workspace.

A parked paste is read in pages of o200k tokens and a line over the per-line cap is split into rows, so no
character of it is out of reach (a secret in it is masked before the split); every other file keeps the
code-file read caps.
"""

from __future__ import annotations

import re

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.core import parked_file_view
from myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.truncation import truncate_file_output
from myrm_agent_harness.agent.meta_tools.file_ops.core.operation_context import ViewRange
from myrm_agent_harness.agent.meta_tools.file_ops.core.parked_file_view import (
    DEFAULT_PAGE_TOKEN_BUDGET,
    MIN_PAGE_TOKEN_BUDGET,
    is_parked_path,
    page_token_budget,
    parked_page_chars,
    wrap_long_lines,
    wrapped_rows_notice,
)
from myrm_agent_harness.agent.meta_tools.file_ops.core.result_formatter import FileContent, ResultFormatter
from myrm_agent_harness.utils.text_utils import get_token_count

_PARKED = ".myrm/pastes/payload_0123456789abcdef.md"
_ROW_NUMBER = re.compile(r"^\s*(\d+)\|", re.MULTILINE)
_PAGE_BUDGETS = [DEFAULT_PAGE_TOKEN_BUDGET, 6_400, MIN_PAGE_TOKEN_BUDGET]


def _ceiling(page_tokens: int) -> int:
    """A page may overshoot its budget by a tenth, and carries a continuation hint of a few dozen tokens."""
    return page_tokens * 110 // 100 + 300


def _floor(page_tokens: int) -> int:
    """A page that is not the last one is cut a line or two short of the budget at most."""
    return page_tokens * 85 // 100


@pytest.mark.parametrize(
    "path",
    [
        ".myrm/pastes/payload_0123456789abcdef.md",
        "./.myrm/pastes/payload_0123456789abcdef.md",
        ".myrm/spillover/payload_0123456789.md",
        "/work/chat-1/.myrm/pastes/payload_0123456789abcdef.md",
        ".myrm\\pastes\\payload_0123456789abcdef.md",
        "~/.myrm/pastes/payload_0123456789abcdef.md",
        ".myrm//pastes/payload_0123456789abcdef.md",
    ],
)
def test_a_file_in_a_directory_the_guard_writes_is_parked(path: str) -> None:
    assert is_parked_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "",
        "notes.md",
        ".myrm/pastes",
        ".myrm/pastes/",
        ".myrm/pastes/../secret.md",
        ".myrm/pastes/sub/payload_0123456789abcdef.md",
        ".myrm/pastes_old/payload_0123456789abcdef.md",
        "pastes/payload_0123456789abcdef.md",
        "_uploaded/report.md",
        ".myrm/config.json",
        ".myrm/checkpoints/state.sqlite",
    ],
)
def test_a_lookalike_or_neighbouring_path_is_not_parked(path: str) -> None:
    assert not is_parked_path(path)


def test_lines_that_fit_are_returned_as_they_are() -> None:
    lines = ["short", "x" * 2000, ""]
    rows, first_split = wrap_long_lines(lines, 2000)
    assert rows is lines
    assert first_split is None


def test_a_long_line_is_split_without_losing_a_character() -> None:
    long_line = "界" * 4500 + "🙂" * 10 + "tail"
    rows, first_split = wrap_long_lines(["head", long_line, "after"], 2000)
    assert first_split == 2
    assert rows[0] == "head"
    assert rows[-1] == "after"
    pieces = rows[1:-1]
    assert [len(piece) for piece in pieces] == [2000, 2000, 514]
    assert "".join(pieces) == long_line


def test_a_line_of_exactly_the_width_is_not_split() -> None:
    rows, first_split = wrap_long_lines(["a" * 2000, "b" * 2001], 2000)
    assert first_split == 2
    assert [len(row) for row in rows] == [2000, 2000, 1]


_SECRET = "ghp_Ab3dE6gH9jK2mN5pQ8sT1vW4yZ7bC0eF3hJ6"
_SECRET_MASKED = "ghp_Ab...3hJ6"


@pytest.mark.parametrize("offset", [100, 1982, 1990, 1999, 2000, 3985])
def test_a_secret_is_masked_wherever_a_row_boundary_falls_in_it(offset: int) -> None:
    line = "a" * (offset - 1) + " " + _SECRET + " " + "b" * 3000
    rows, first_split = wrap_long_lines([line], 2000)
    assert first_split == 1
    joined = "".join(rows)
    assert _SECRET_MASKED in joined
    assert _SECRET[8:30] not in joined
    assert _SECRET[:20] not in joined


def test_a_line_that_fits_is_left_to_the_redaction_of_the_tool_output() -> None:
    line = "key " + _SECRET
    assert wrap_long_lines([line], 2000) == ([line], None)


def test_a_long_line_that_redaction_shrinks_under_the_width_is_not_a_split(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parked_file_view, "redact_sensitive_text", lambda _line: "masked")
    lines = ["head", "x" * 5000]
    assert wrap_long_lines(lines, 2000) == (lines, None)


def test_the_notice_names_the_width_and_the_last_line_whose_number_still_matches() -> None:
    notice = wrapped_rows_notice(2000, 7)
    assert "2,000 characters" in notice
    assert "up to line 7" in notice


def _render(lines: list[str], *, path: str, start: int = 1, max_line_length: int | None = 2000) -> str:
    content = FileContent(
        path=path,
        display_path=path,
        lines=lines,
        view_range=ViewRange(start=start, end=-1) if start > 1 else None,
    )
    return ResultFormatter.format_file_content(content, max_line_length=max_line_length)


def _cut_page(rendered: str, page_tokens: int = DEFAULT_PAGE_TOKEN_BUDGET) -> tuple[str, bool, dict[str, object]]:
    """One page of a parked file's rendered output, cut the way ``text_paths`` cuts it."""
    return truncate_file_output(
        rendered, max_chars=parked_page_chars(rendered, page_tokens), path_str=_PARKED, max_lines=None
    )


def _read_pages(lines: list[str], page_tokens: int = DEFAULT_PAGE_TOKEN_BUDGET) -> list[tuple[str, dict[str, object]]]:
    """Read a parked file page by page the way the model does: follow ``next_offset`` until the end."""
    pages: list[tuple[str, dict[str, object]]] = []
    start = 1
    while True:
        text, truncated, meta = _cut_page(_render(lines, path=_PARKED, start=start), page_tokens)
        pages.append((text, meta))
        if not truncated:
            return pages
        next_offset = meta["next_offset"]
        assert isinstance(next_offset, int)
        assert next_offset > start
        start = next_offset


def _prose(count: int) -> list[str]:
    return [
        f"Clause {n}. The supplier delivers within thirty days; late delivery incurs a penalty." for n in range(count)
    ]


def _dense(count: int) -> list[str]:
    return [f"{n:08x}" + "9f3a7c01e5b2d684" * 6 for n in range(count)]


def test_a_text_that_fits_one_page_is_not_cut() -> None:
    rendered = _render(_prose(300), path=_PARKED)
    text, truncated, meta = _cut_page(rendered)
    assert (text, truncated, meta) == (rendered, False, {})


@pytest.mark.parametrize(
    ("name", "lines"),
    [
        ("prose", _prose(9000)),
        ("dense hex", _dense(3500)),
        ("dense head, prose tail", _dense(1500) + _prose(8000)),
    ],
)
@pytest.mark.parametrize("page_tokens", _PAGE_BUDGETS)
def test_every_page_is_filled_to_the_token_budget_and_the_pages_cover_the_text(
    name: str, lines: list[str], page_tokens: int
) -> None:
    pages = _read_pages(lines, page_tokens)
    assert len(pages) > 1, name
    shown: list[int] = []
    for index, (text, _meta) in enumerate(pages):
        tokens = get_token_count(text)
        assert tokens <= _ceiling(page_tokens), (name, page_tokens)
        if index < len(pages) - 1:
            assert tokens >= _floor(page_tokens), (name, page_tokens)
        shown.extend(int(number) for number in _ROW_NUMBER.findall(text))
    assert shown == list(range(1, len(lines) + 1)), name


@pytest.mark.parametrize(
    ("window", "budget"),
    [
        (None, 20_000),
        (0, 20_000),
        (-1, 20_000),
        (4_096, 2_000),
        (16_384, 2_000),
        (20_000, 2_000),
        (32_000, 3_200),
        (64_000, 6_400),
        (65_536, 6_553),
        (65_537, 20_000),
        (131_072, 20_000),
        (1_000_000, 20_000),
    ],
)
def test_a_window_within_the_medium_tier_gets_a_tenth_of_it_and_any_other_window_the_full_page(
    window: int | None, budget: int
) -> None:
    assert page_token_budget(window) == budget


def test_a_page_is_cut_the_same_way_every_time() -> None:
    rendered = _render(_prose(9000), path=_PARKED)
    first = _cut_page(rendered)
    assert _cut_page(rendered) == first


def test_the_other_files_keep_the_clamped_line_and_no_notice() -> None:
    rendered = _render(["head", "x" * 5000, "tail"], path="src/app.py")
    assert "... [truncated]" in rendered
    assert "split into rows" not in rendered
    assert "(3 lines)" in rendered
    assert "x" * 2001 not in rendered


def test_a_parked_long_line_becomes_rows_with_a_notice() -> None:
    rendered = _render(["head", "x" * 4500, "tail"], path=_PARKED)
    assert "... [truncated]" not in rendered
    assert "(5 lines)" in rendered
    assert wrapped_rows_notice(2000, 2) in rendered
    assert rendered.count("x") == 4500
    assert [int(number) for number in _ROW_NUMBER.findall(rendered)] == [1, 2, 3, 4, 5]


def test_a_parked_text_without_a_long_line_has_no_notice() -> None:
    rendered = _render(["head", "short", "tail"], path=_PARKED)
    assert "split into rows" not in rendered
    assert "(3 lines)" in rendered


def test_without_a_line_cap_a_parked_line_is_left_whole() -> None:
    rendered = _render(["x" * 4500], path=_PARKED, max_line_length=None)
    assert "split into rows" not in rendered
    assert "x" * 4500 in rendered


def test_a_range_over_a_parked_text_counts_the_same_rows_as_the_whole_read() -> None:
    lines = ["head", "x" * 4500, "tail"]
    whole = _render(lines, path=_PARKED)
    ranged = _render(lines, path=_PARKED, start=3)
    assert wrapped_rows_notice(2000, 2) in ranged
    ranged_rows = [row for row in ranged.splitlines() if _ROW_NUMBER.match(row)]
    assert ranged_rows
    assert all(row in whole.splitlines() for row in ranged_rows)
    assert ranged_rows[-1].endswith("|tail")
    assert ranged_rows[0].startswith("     3|")
