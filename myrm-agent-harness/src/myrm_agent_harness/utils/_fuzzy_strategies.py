"""The strategy chain behind fuzzy_match: Unicode normalization and the eight finders, cheapest first.

[POS]
Private to utils.fuzzy_match. ``STRATEGIES`` lists (name, finder, confidence) in the order they are tried; a finder
returns the text of ``content`` that matches ``fragment``, or None.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from difflib import SequenceMatcher

_UNICODE_MAP: dict[str, str] = {
    "\u2018": "'",  # left single quote
    "\u2019": "'",  # right single quote
    "\u201c": '"',  # left double quote
    "\u201d": '"',  # right double quote
    "\u2013": "-",  # en dash
    "\u2014": "--",  # em dash
    "\u2026": "...",  # ellipsis
    "\u00a0": " ",  # non-breaking space
    "\u200b": "",  # zero-width space
    "\u200c": "",  # zero-width non-joiner
    "\u200d": "",  # zero-width joiner
    "\ufeff": "",  # BOM / zero-width no-break space
}

_UNICODE_RE = re.compile("|".join(re.escape(k) for k in _UNICODE_MAP))
_HAS_NON_ASCII_RE = re.compile(r"[^\x00-\x7f]")
_WHITESPACE_COLLAPSE_RE = re.compile(r"[ \t]+")
_ESCAPE_MAP = {"\\n": "\n", "\\t": "\t", "\\r": "\r"}

_BLOCK_SIMILARITY_THRESHOLD = 0.60
_BLOCK_LINE_COUNT_TOLERANCE = 0.20


def normalize_unicode(text: str) -> str:
    """Replace common Unicode variants with ASCII equivalents."""
    return _UNICODE_RE.sub(lambda m: _UNICODE_MAP[m.group()], text)


def needs_unicode_normalization(text: str) -> bool:
    return bool(_HAS_NON_ASCII_RE.search(text))


def _strip_lines(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines())


def _collapse_whitespace(text: str) -> str:
    return "\n".join(_WHITESPACE_COLLAPSE_RE.sub(" ", line).strip() for line in text.splitlines())


def _extract_relative_indents(text: str) -> tuple[list[str], list[int]]:
    """Extract lines and relative indent deltas.

    Returns (stripped_lines, indent_deltas) where indent_deltas[i] is
    the indent change from line i-1 to line i (first line delta is 0).
    """
    lines = text.splitlines()
    stripped: list[str] = []
    deltas: list[int] = []
    prev_indent = 0
    for line in lines:
        content = line.lstrip()
        indent = len(line) - len(content)
        stripped.append(content)
        deltas.append(indent - prev_indent)
        prev_indent = indent
    return stripped, deltas


def _normalize_escapes(text: str) -> str:
    """Convert literal escape sequences to actual characters."""
    result = text
    for escaped, actual in _ESCAPE_MAP.items():
        result = result.replace(escaped, actual)
    return result


def _line_similarity(a: str, b: str) -> float:
    """Compute similarity ratio between two strings."""
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _find_exact(content: str, fragment: str) -> str | None:
    if fragment in content:
        return fragment
    return None


def _find_line_trimmed(content: str, fragment: str) -> str | None:
    norm_frag = _strip_lines(fragment)
    lines = content.splitlines()
    frag_lines = norm_frag.splitlines()
    frag_len = len(frag_lines)
    if frag_len == 0:
        return None

    for i in range(len(lines) - frag_len + 1):
        window = lines[i : i + frag_len]
        if all(a.strip() == b for a, b in zip(window, frag_lines, strict=False)):
            return "\n".join(window)
    return None


def _find_whitespace_normalized(content: str, fragment: str) -> str | None:
    norm_frag = _collapse_whitespace(fragment)
    lines = content.splitlines()
    frag_lines = norm_frag.splitlines()
    frag_len = len(frag_lines)
    if frag_len == 0:
        return None

    for i in range(len(lines) - frag_len + 1):
        window = lines[i : i + frag_len]
        norm_window = [_WHITESPACE_COLLAPSE_RE.sub(" ", line).strip() for line in window]
        if norm_window == frag_lines:
            return "\n".join(window)
    return None


def _find_indent_flexible(content: str, fragment: str) -> str | None:
    frag_stripped, frag_deltas = _extract_relative_indents(fragment)
    frag_len = len(frag_stripped)
    if frag_len == 0:
        return None

    lines = content.splitlines()
    for i in range(len(lines) - frag_len + 1):
        window = lines[i : i + frag_len]
        win_stripped, win_deltas = _extract_relative_indents("\n".join(window))
        if win_stripped == frag_stripped and win_deltas == frag_deltas:
            return "\n".join(window)
    return None


def _find_escape_normalized(content: str, fragment: str) -> str | None:
    norm_frag = _normalize_escapes(fragment)
    if norm_frag == fragment:
        return None
    if norm_frag in content:
        return norm_frag
    return None


def _find_trimmed_boundary(content: str, fragment: str) -> str | None:
    """Match after trimming only the first and last line of the fragment."""
    frag_lines = fragment.splitlines()
    if len(frag_lines) < 1:
        return None

    trimmed_first = frag_lines[0].strip()
    trimmed_last = frag_lines[-1].strip() if len(frag_lines) > 1 else trimmed_first
    middle = frag_lines[1:-1] if len(frag_lines) > 2 else []

    lines = content.splitlines()
    frag_len = len(frag_lines)

    for i in range(len(lines) - frag_len + 1):
        if lines[i].strip() != trimmed_first:
            continue
        if len(frag_lines) > 1 and lines[i + frag_len - 1].strip() != trimmed_last:
            continue
        if middle and lines[i + 1 : i + frag_len - 1] != middle:
            continue
        if not middle and frag_len == 1:
            return lines[i]
        return "\n".join(lines[i : i + frag_len])
    return None


def _find_block_anchored(content: str, fragment: str) -> str | None:
    frag_lines = fragment.splitlines()
    if len(frag_lines) < 3:
        return None

    first_stripped = frag_lines[0].strip()
    last_stripped = frag_lines[-1].strip()
    frag_len = len(frag_lines)
    min_lines = int(frag_len * (1 - _BLOCK_LINE_COUNT_TOLERANCE))
    max_lines = int(frag_len * (1 + _BLOCK_LINE_COUNT_TOLERANCE))

    lines = content.splitlines()
    candidates: list[str] = []

    for i, line in enumerate(lines):
        if line.strip() != first_stripped:
            continue

        for end in range(i + min_lines - 1, min(i + max_lines, len(lines))):
            if lines[end].strip() != last_stripped:
                continue

            window = lines[i : end + 1]
            window_inner = [ln.strip() for ln in window[1:-1]]
            frag_inner = [ln.strip() for ln in frag_lines[1:-1]]

            if not frag_inner:
                candidates.append("\n".join(window))
                continue

            total_sim = sum(
                max(_line_similarity(fl, wl) for wl in window_inner) if window_inner else 0.0 for fl in frag_inner
            )
            avg_sim = total_sim / len(frag_inner)

            if avg_sim >= _BLOCK_SIMILARITY_THRESHOLD:
                candidates.append("\n".join(window))

    if len(candidates) == 1:
        return candidates[0]
    return None


_CONTEXT_AWARE_SIMILARITY_THRESHOLD = 0.50


def _find_context_aware(content: str, fragment: str) -> str | None:
    """Match by first/last line anchor with relaxed 50% middle-line similarity."""
    frag_lines = fragment.splitlines()
    if len(frag_lines) < 3:
        return None

    while frag_lines and frag_lines[-1] == "":
        frag_lines.pop()

    first_line = frag_lines[0].strip()
    last_line = frag_lines[-1].strip()

    lines = content.splitlines()
    frag_len = len(frag_lines)

    for i in range(len(lines)):
        if lines[i].strip() != first_line:
            continue

        end = i + frag_len - 1
        if end >= len(lines):
            continue
        if lines[end].strip() != last_line:
            continue

        block = lines[i : end + 1]
        if len(block) != frag_len:
            continue

        matching = 0
        total_non_empty = 0
        for k in range(1, len(block) - 1):
            bl = block[k].strip()
            fl = frag_lines[k].strip()
            if bl or fl:
                total_non_empty += 1
                if bl == fl:
                    matching += 1

        if total_non_empty == 0 or matching / total_non_empty >= _CONTEXT_AWARE_SIMILARITY_THRESHOLD:
            return "\n".join(block)

    return None


STRATEGIES: tuple[tuple[str, Callable[[str, str], str | None], float], ...] = (
    ("exact", _find_exact, 1.0),
    ("line_trimmed", _find_line_trimmed, 0.95),
    ("whitespace_normalized", _find_whitespace_normalized, 0.90),
    ("indent_flexible", _find_indent_flexible, 0.85),
    ("escape_normalized", _find_escape_normalized, 0.80),
    ("trimmed_boundary", _find_trimmed_boundary, 0.75),
    ("block_anchored", _find_block_anchored, 0.60),
    ("context_aware", _find_context_aware, 0.50),
)
