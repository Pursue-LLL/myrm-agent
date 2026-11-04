"""Sanitize web-extracted markdown before model delivery.

Strips inline base64 image blobs that waste context tokens without adding
readable content for text models.

The scan is anchored on the literal ``data:image/`` and only ever looks a
bounded distance around each occurrence, so its cost grows linearly with the
input: a hostile page cannot stall the process with pathological bracket or
whitespace runs (regex alternatives that start from ``![`` or ``(`` rescan to
the end of the text from every start position).

[OUTPUT]
- strip_base64_images_from_markdown: replace inline base64 images with placeholders

[POS]
web_fetch toolkit preprocessing (delivery only, not Turn1 schema).
"""

from __future__ import annotations

import re

_DATA_URI_START = "data:image/"
_BASE64_TAG = ";base64,"
# Real MIME subtypes are a few characters long; the bound keeps the per-occurrence scan constant-size.
_MAX_MIME_CHARS = 100
# Longer alt text stays in place (the blob is still replaced); the bound keeps the backward look-up constant-size.
_MAX_ALT_CHARS = 1_000

_PAYLOAD = re.compile(r"[A-Za-z0-9+/=]*")
_PAYLOAD_WITH_WHITESPACE = re.compile(r"[A-Za-z0-9+/=\s]*")

_Replacement = tuple[int, int, str]


def _run_end(pattern: re.Pattern[str], text: str, position: int) -> int:
    """End of the run ``pattern`` accepts from ``position`` (``position`` itself when the run is empty)."""
    match = pattern.match(text, position)
    return match.end() if match else position


def _alt_start(text: str, paren: int, floor: int) -> int | None:
    """Index of the ``![`` whose alt text ends with the ``]`` right before ``paren``."""
    close = paren - 1
    if close < floor or text[close] != "]":
        return None
    lower = max(floor, close - _MAX_ALT_CHARS - 2)
    previous_close = text.rfind("]", lower, close)
    opener = text.find("![", previous_close + 1 if previous_close >= 0 else lower, close)
    return opener if opener >= 0 else None


def _wrapped_replacement(text: str, start: int, wrapped_end: int, floor: int) -> _Replacement | None:
    """Replacement for ``(<uri>)`` or ``![alt](<uri>)`` whose closing parenthesis is ``text[wrapped_end]``."""
    open_paren = start
    while open_paren > floor and text[open_paren - 1].isspace():
        open_paren -= 1
    if open_paren <= floor or text[open_paren - 1] != "(":
        return None
    open_paren -= 1
    alt_start = _alt_start(text, open_paren, floor)
    if alt_start is None:
        return open_paren, wrapped_end + 1, "[IMAGE]"
    alt = text[alt_start + 2 : open_paren - 1].strip()
    return alt_start, wrapped_end + 1, f"[IMAGE: {alt}]" if alt else "[IMAGE]"


def _replacement_at(text: str, start: int, floor: int) -> _Replacement | None:
    """Replacement for the data URI starting at ``start``; ``None`` when it is not a base64 payload.

    ``floor`` is the first character not yet consumed by an earlier replacement.
    """
    mime_from = start + len(_DATA_URI_START)
    semicolon = text.find(";", mime_from, mime_from + _MAX_MIME_CHARS + 1)
    if semicolon <= mime_from or not text.startswith(_BASE64_TAG, semicolon):
        return None
    payload_from = semicolon + len(_BASE64_TAG)

    wrapped_end = _run_end(_PAYLOAD_WITH_WHITESPACE, text, payload_from)
    if wrapped_end > payload_from and text.startswith(")", wrapped_end):
        wrapped = _wrapped_replacement(text, start, wrapped_end, floor)
        if wrapped is not None:
            return wrapped
    bare_end = _run_end(_PAYLOAD, text, payload_from)
    return (start, bare_end, "[IMAGE]") if bare_end > payload_from else None


def strip_base64_images_from_markdown(text: str) -> str:
    """Replace inline base64 images with compact placeholders.

    ``![alt](data:...)`` becomes ``[IMAGE: alt]``; any other ``data:image/...;base64,...`` form
    (parenthesised link target, HTML attribute, bare text) becomes ``[IMAGE]``.
    """
    start = text.find(_DATA_URI_START)
    if start < 0:
        return text
    parts: list[str] = []
    cursor = 0
    while start >= 0:
        replacement = _replacement_at(text, start, cursor)
        if replacement is None:
            start = text.find(_DATA_URI_START, start + 1)
            continue
        replace_from, replace_to, placeholder = replacement
        parts.append(text[cursor:replace_from])
        parts.append(placeholder)
        cursor = replace_to
        start = text.find(_DATA_URI_START, cursor)
    parts.append(text[cursor:])
    return "".join(parts)
