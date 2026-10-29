"""Bounded regex replacement, the ReDoS guard of every redaction pass.

A regex that backtracks on adversarial text takes time that grows with the text, so a long text is cut into
overlapping chunks and each chunk is matched on its own.

[INPUT]
- (none) — standard library only

[OUTPUT]
- ``_replace_pattern_bounded(text, pattern, replacer)`` — ``pattern.sub`` that stays linear on a long text

[POS]
Leaf helper of the redaction domain; ``engine.py``, ``header_patterns.py`` and ``command_patterns.py`` apply their
patterns through it.
"""

from __future__ import annotations

import re
from collections.abc import Callable

# ── Bounded replace constants (防ReDoS) ──────────────────────────
_REDACT_REGEX_CHUNK_THRESHOLD = 32768  # 32KB
_REDACT_REGEX_CHUNK_SIZE = 16384  # 16KB
_CHUNK_OVERLAP = 4096  # covers RSA-4096 PEM (~3200 chars) + margin


def _replace_pattern_bounded(
    text: str,
    pattern: re.Pattern[str],
    replacer: str | Callable[[re.Match[str]], str],
    chunk_threshold: int = _REDACT_REGEX_CHUNK_THRESHOLD,
    chunk_size: int = _REDACT_REGEX_CHUNK_SIZE,
) -> str:
    """Replace pattern with bounded chunking to prevent ReDoS.

    Each chunk extends by ``_CHUNK_OVERLAP`` bytes into the next chunk
    so patterns spanning a boundary are matched intact.  Deduplication
    via ``seen_starts`` ensures overlap-region matches are not applied
    twice.  Results are assembled with a single forward join (O(n)).

    Args:
        text: Input text
        pattern: Compiled regex pattern
        replacer: Replacement string or callable
        chunk_threshold: Min text length to trigger chunking (default: 32KB)
        chunk_size: Size of each chunk (default: 16KB)

    Returns:
        Redacted text
    """
    if len(text) <= chunk_threshold:
        return pattern.sub(replacer, text)

    matches: list[tuple[int, int, str]] = []
    seen_starts: set[int] = set()

    pos = 0
    while pos < len(text):
        chunk_end = min(pos + chunk_size + _CHUNK_OVERLAP, len(text))
        chunk = text[pos:chunk_end]

        for m in pattern.finditer(chunk):
            abs_start = pos + m.start()
            if abs_start in seen_starts:
                continue
            seen_starts.add(abs_start)
            abs_end = pos + m.end()
            repl = replacer(m) if callable(replacer) else m.expand(replacer)
            matches.append((abs_start, abs_end, repl))

        pos += chunk_size

    if not matches:
        return text

    parts: list[str] = []
    last_end = 0
    for abs_start, abs_end, repl in matches:
        # 分块重叠区可能产出区间重叠的 match（如 IGNORECASE 下 `[A-Z_]` 前缀贪婪
        # 吃掉 `KEY` 前 50 个连续字母产生长 key match，与后续短 key match 区间重叠）。
        # 重叠 match 若一并拼接会把文本重复插入，须跳过（seen_starts 只防同 start）。
        if abs_start < last_end:
            continue
        parts.append(text[last_end:abs_start])
        parts.append(repl)
        last_end = abs_end
    parts.append(text[last_end:])
    return "".join(parts)
