"""How file_read_tool shows a long text the context guard parked in the workspace.

A parked paste is not source code. It can be one 60,000-character line (minified JSON, base64, an article
pasted without line breaks), and it runs to several times the size of an ordinary read page. The read caps are
sized for code files: they hand the model a page of 10,000 characters, so a large paste costs one model call per
10,000 characters, and they cut a line at 2,000 characters, so the rest of a long line cannot be read at all.
Files in the two parked directories get their own view instead: a long line is split into rows rather than cut,
and a page holds a fixed number of real tokens whatever the density of the text.

[INPUT]
- agent.context_guard::KEPT_SPILLOVER_DIR, TRANSIENT_SPILLOVER_DIR (POS: the directories the guard writes to)
- utils.text_utils::get_token_count (POS: real token count)
- file_read_truncation::truncate_file_output (POS: complete-line page cut with a continuation offset)

[OUTPUT]
- is_parked_path: whether a path names a file the context guard parked
- wrap_long_lines: split lines over a width into rows, without losing a character
- wrapped_rows_notice: the one-line note that row numbers no longer match the file's line numbers
- truncate_parked_page: one page of a parked file's rendered output, sized in real tokens

[POS]
View rules for parked-text files; result_formatter splits the rows, file_read_handlers sizes the page.
"""

from __future__ import annotations

import posixpath

from myrm_agent_harness.agent.context_guard import KEPT_SPILLOVER_DIR, TRANSIENT_SPILLOVER_DIR
from myrm_agent_harness.utils.text_utils import get_token_count

from .file_read_truncation import truncate_file_output

# A page is 20,000 real tokens: a sixth of a 128k window, and four pages fit the 100,000-token per-run result
# budget, so a long paste is read in a few calls without one page crowding the window out.
PAGE_TOKEN_BUDGET = 20_000
# A page may overshoot by a tenth rather than cut a text a few lines short of fitting.
_PAGE_TOLERANCE_PERCENT = 10
# First window to measure: 4 characters per token, which prose stays under and dense text overshoots.
_FIRST_GUESS_CHARS = PAGE_TOKEN_BUDGET * 4
_REFINE_ROUNDS = 5
# Each refinement aims a little under the budget so the next measurement lands inside the tolerance.
_REFINE_AIM_PERCENT = 97

_PARKED_DIRS = frozenset({KEPT_SPILLOVER_DIR, TRANSIENT_SPILLOVER_DIR})


def is_parked_path(path: str) -> bool:
    """Whether *path* names a file directly inside a directory the context guard parks text in.

    The path is judged after normalisation, so ``.myrm/pastes/../x.md`` (which leaves the directory) is not
    parked while ``./.myrm/pastes/x.md``, an absolute path and a backslash path to the same place are.
    """
    segments = posixpath.normpath(path.replace("\\", "/")).split("/")
    return len(segments) >= 3 and "/".join(segments[-3:-1]) in _PARKED_DIRS


def wrap_long_lines(lines: list[str], width: int) -> tuple[list[str], int | None]:
    """Split every line longer than *width* characters into rows of at most *width*, on code-point boundaries.

    Returns the rows and the 1-based number of the first line that was split (``None``, with *lines* itself,
    when no line was).
    """
    first_split: int | None = None
    rows: list[str] = []
    for number, line in enumerate(lines, start=1):
        if len(line) <= width:
            rows.append(line)
            continue
        if first_split is None:
            first_split = number
        rows.extend(line[start : start + width] for start in range(0, len(line), width))
    return (lines if first_split is None else rows), first_split


def wrapped_rows_notice(width: int, first_split_line: int) -> str:
    """Tell the model that row numbers match the file's line numbers only up to the first split line."""
    return (
        f"[Lines longer than {width:,} characters are split into rows of that length, so the numbers below count "
        f"rows: they match the file's own line numbers only up to line {first_split_line}.]"
    )


def _page_chars(output: str) -> int:
    """Characters from the start of *output* that make up one page of ``PAGE_TOKEN_BUDGET`` real tokens.

    Only the window that becomes the page is measured, so the cost does not grow with the size of the file.
    """
    ceiling = PAGE_TOKEN_BUDGET * (100 + _PAGE_TOLERANCE_PERCENT) // 100
    floor = PAGE_TOKEN_BUDGET * (100 - _PAGE_TOLERANCE_PERCENT) // 100
    chars = min(len(output), _FIRST_GUESS_CHARS)
    fitting = 0
    for _ in range(_REFINE_ROUNDS):
        tokens = get_token_count(output[:chars])
        if tokens <= ceiling:
            fitting = max(fitting, chars)
            if chars == len(output) or tokens >= floor:
                return chars
        chars = min(len(output), max(1, chars * PAGE_TOKEN_BUDGET * _REFINE_AIM_PERCENT // (max(tokens, 1) * 100)))
    # The density kept jumping between windows: halve until a window is known to fit.
    while not fitting:
        chars = max(1, chars // 2)
        if chars == 1 or get_token_count(output[:chars]) <= ceiling:
            fitting = chars
    return fitting


def truncate_parked_page(output: str, *, path_str: str, max_lines: int | None) -> tuple[str, bool, dict[str, object]]:
    """Cut the rendered output of a parked file to one page, with the continuation offset of the next one.

    Same contract as ``truncate_file_output``; the page size is ``PAGE_TOKEN_BUDGET`` real tokens instead of a
    fixed number of characters.
    """
    return truncate_file_output(output, max_chars=_page_chars(output), path_str=path_str, max_lines=max_lines)
