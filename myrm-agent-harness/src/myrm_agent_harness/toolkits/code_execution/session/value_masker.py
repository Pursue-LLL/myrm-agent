"""Exact-value masking of the credentials a command was given.

[INPUT]
(standard library only)

[OUTPUT]
ValueMasker: hides given secret values in a text stream, also when a value is split across reads.
printed_forms: a credential and the forms a client prints it in (URL-percent-encoded, JSON-escaped), as the values to hide.
MASK: the text a hidden value is replaced with.
MIN_MASKED_LENGTH: the shortest value that is masked.

[POS]
Pattern-based scrubbing (``scrub_sensitive_info``) recognises credentials by their shape, so a password a user typed
for one command, or a token under an arbitrary variable name, passes it when the command prints it (``set -x``,
``env``, a verbose client). The masker knows the values themselves. It works on the decoded output of one command,
before that output is teed, streamed or returned, so every copy of it is masked. The result is exactly what masking
the whole output in one piece would give, wherever the reads were cut: a read ending in the beginning of a value is
held back until the next read shows whether the value continues.

Limits: a value shorter than ``MIN_MASKED_LENGTH`` is left alone (it would mangle ordinary output and protects
little); a value of 4 to 7 characters is hidden wherever it appears, inside longer words too (``root`` in ``rooted``);
a value the command re-encodes any other way (base64, ``+`` for a space, lower-case hex digits, HTML entities) is not
recognised; a stream that ends in the middle of a value releases that fragment.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from urllib.parse import quote

MASK = "***"
MIN_MASKED_LENGTH = 4


def printed_forms(values: Iterable[str]) -> list[str]:
    """The values to hide for these credentials: each one, and the forms a client prints it in.

    A client that puts a credential in a URL writes it percent-encoded (most encoders also escape ``!'()*``, and
    JavaScript's ``encodeURIComponent`` does not); one that echoes a request body writes it as a JSON string. A form
    is added only where it differs from the value, so a plain token costs nothing extra. A value under
    ``MIN_MASKED_LENGTH`` has no forms: it is left alone, and so is anything derived from it.
    """
    forms: set[str] = set()
    for value in values:
        if len(value) >= MIN_MASKED_LENGTH:
            forms.update(
                (
                    value,
                    quote(value, safe=""),
                    quote(value, safe="!'()*"),
                    json.dumps(value, ensure_ascii=False)[1:-1],
                )
            )
    return sorted(forms)


class ValueMasker:
    """Replaces every occurrence of the given values; the longest value wins where several start together."""

    def __init__(self, values: Iterable[str]) -> None:
        self._values = tuple(sorted({v for v in values if len(v) >= MIN_MASKED_LENGTH}, key=len, reverse=True))
        self._pattern = re.compile("|".join(map(re.escape, self._values))) if self._values else None
        self._first_chars = frozenset(v[0] for v in self._values)
        self._longest = len(self._values[0]) if self._values else 0
        self._carry = ""

    def feed(self, text: str) -> str:
        """Return the part of ``text`` that is settled: masked, and not the start of a value that may continue."""
        pattern = self._pattern
        if pattern is None:
            return text
        data = self._carry + text
        found = self._find(pattern, data)
        hold_from = self._hold_from(data, found)
        self._carry = data[hold_from:]
        head = data[:hold_from]
        return pattern.sub(MASK, head) if found else head

    def flush(self) -> str:
        """Return what ``feed`` still holds, masked; call when the stream has ended."""
        pattern = self._pattern
        if pattern is None:
            return ""
        carry, self._carry = self._carry, ""
        return pattern.sub(MASK, carry)

    def _find(self, pattern: re.Pattern[str], data: str) -> list[tuple[int, int]]:
        """The spans of the values in ``data``; most output holds none, which plain substring searches rule out cheaply."""
        if not any(value in data for value in self._values):
            return []
        return [m.span() for m in pattern.finditer(data)]

    def _hold_from(self, data: str, found: list[tuple[int, int]]) -> int:
        """Where the tail of ``data`` starts that a later read could still turn into a value.

        That is the earliest position whose remaining text is the beginning of a longer value and does not lie
        inside a value already found there (masking the whole output in one piece would have consumed it).
        """
        for start in range(max(0, len(data) - self._longest + 1), len(data)):
            if data[start] not in self._first_chars:
                continue
            tail = data[start:]
            if not any(len(v) > len(tail) and v.startswith(tail) for v in self._values):
                continue
            if any(s < start < e for s, e in found):
                continue
            return start
        return len(data)
