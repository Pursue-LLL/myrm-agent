"""How file_read_tool shows a long text the context guard parked in the workspace.

A parked paste is not source code. It can be one 60,000-character line (minified JSON, base64, an article
pasted without line breaks), and it runs to several times the size of an ordinary read page. The read caps are
sized for code files: they hand the model a page of 10,000 characters, so a large paste costs one model call per
10,000 characters, and they cut a line at 2,000 characters, so the rest of a long line cannot be read at all.
Files in the two parked directories get their own view instead: a long line is split into rows rather than cut,
and a page holds a number of o200k tokens that follows the model's window, not the density of the text.

[INPUT]
- agent.context_guard::KEPT_SPILLOVER_DIR, TRANSIENT_SPILLOVER_DIR (POS: the directories the guard writes to)
- agent.security.redact::redact_sensitive_text (POS: tool output redaction)
- core.config.model_tier::ModelTier, infer_model_tier (POS: the window tiers)
- utils.text_utils::get_token_count (POS: tiktoken count, o200k)

[OUTPUT]
- is_parked_path: whether a path names a file the context guard parked
- wrap_long_lines: split lines over a width into rows, after redacting the lines it splits
- wrapped_rows_notice: the one-line note that row numbers no longer match the file's line numbers
- page_token_budget: how many o200k tokens one page holds for a model with a given window
- parked_page_chars: how many characters of a parked file's rendered output make up one page of that many tokens

[POS]
View rules for parked-text files; result_formatter splits the rows, file_read.text_paths sizes the page.
"""

from __future__ import annotations

import posixpath

from myrm_agent_harness.agent.context_guard import KEPT_SPILLOVER_DIR, TRANSIENT_SPILLOVER_DIR
from myrm_agent_harness.agent.security.redact import redact_sensitive_text
from myrm_agent_harness.core.config.model_tier import ModelTier, infer_model_tier
from myrm_agent_harness.utils.text_utils import get_token_count

# A page is 20,000 o200k tokens (16% of a 128k window), so a long paste is read in a few calls. A model with another
# tokenizer sees more tokens in the same page (CJK, for one).
PAGE_TOKEN_BUDGET = 20_000
# A model whose window is in the MEDIUM tier or below gets a page of a tenth of its window instead: the context pruner
# keeps the five most recent tool results in full (``ContextConfig.keep_recent_calls``), so five consecutive pages take
# half the window.
_SMALL_WINDOW_PAGE_DIVISOR = 10
# Floor on a page, so a very small window does not turn one paste into dozens of model calls. A window under 20,000
# tokens therefore gets more than a tenth of it per page.
MIN_PAGE_TOKEN_BUDGET = 2_000
# A page may overshoot by a tenth rather than cut a text a few lines short of fitting.
_PAGE_TOLERANCE_PERCENT = 10
# First window to measure: 4 characters per token, which prose stays under and dense text overshoots.
_FIRST_GUESS_CHARS_PER_TOKEN = 4
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

    A line is redacted before it is split: the tool output is redacted once it is laid out in rows, and a secret cut
    in two by a row boundary, with a line number between the halves, no longer matches any pattern.

    Returns the rows and the 1-based number of the first line that was split (``None``, with *lines* itself,
    when no line was).
    """
    first_split: int | None = None
    rows: list[str] = []
    for number, line in enumerate(lines, start=1):
        if len(line) <= width:
            rows.append(line)
            continue
        line = redact_sensitive_text(line)
        pieces = [line[start : start + width] for start in range(0, len(line), width)]
        if first_split is None and len(pieces) > 1:
            first_split = number
        rows.extend(pieces)
    return (lines if first_split is None else rows), first_split


def wrapped_rows_notice(width: int, first_split_line: int) -> str:
    """Tell the model that row numbers match the file's line numbers only up to the first split line."""
    return (
        f"[Lines longer than {width:,} characters are split into rows of that length, so the numbers below count "
        f"rows: they match the file's own line numbers only up to line {first_split_line}.]"
    )


def page_token_budget(window_tokens: int | None) -> int:
    """o200k tokens in one page for a model whose context window is *window_tokens* (``None``: not reported).

    A window in the MEDIUM tier or below gets a tenth of it, at least ``MIN_PAGE_TOKEN_BUDGET``. A larger or unknown
    window, and a value that is not a window (zero, negative), gets ``PAGE_TOKEN_BUDGET``.
    """
    if window_tokens is None or window_tokens <= 0 or infer_model_tier("", None, window_tokens) is ModelTier.STRONG:
        return PAGE_TOKEN_BUDGET
    return max(window_tokens // _SMALL_WINDOW_PAGE_DIVISOR, MIN_PAGE_TOKEN_BUDGET)


def parked_page_chars(output: str, page_tokens: int = PAGE_TOKEN_BUDGET) -> int:
    """Characters from the start of *output* that make up one page of *page_tokens* o200k tokens.

    Only the window that becomes the page is measured, so the cost does not grow with the size of the file.
    """
    ceiling = page_tokens * (100 + _PAGE_TOLERANCE_PERCENT) // 100
    floor = page_tokens * (100 - _PAGE_TOLERANCE_PERCENT) // 100
    chars = min(len(output), page_tokens * _FIRST_GUESS_CHARS_PER_TOKEN)
    fitting = 0
    for _ in range(_REFINE_ROUNDS):
        tokens = get_token_count(output[:chars])
        if tokens <= ceiling:
            fitting = max(fitting, chars)
            if chars == len(output) or tokens >= floor:
                return chars
        chars = min(len(output), max(1, chars * page_tokens * _REFINE_AIM_PERCENT // (max(tokens, 1) * 100)))
    # The density kept jumping between windows: halve until a window is known to fit.
    while not fitting:
        chars = max(1, chars // 2)
        if chars == 1 or get_token_count(output[:chars]) <= ceiling:
            fitting = chars
    return fitting
