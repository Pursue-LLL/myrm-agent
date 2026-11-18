"""Escaped line breaks: the leak detector reads a newline, return or tab escaped in JSON text as whitespace.

A tool result reaches the guardrail as JSON text, where a line break is the two characters backslash and ``n``. The
matchers end a value at whitespace, so on that text a value runs on across the break into the next line, and masking it
hides the lines it swallowed (a listing whose names hold no space became one token). Inside the JSON value a text starts
with, the three breaks are read as whitespace while the matchers run and are put back in what they return.

[INPUT]
- (none: standard library only)

[OUTPUT]
- reading_breaks(): decorator for a function that reads text (a scan); it gets the text with the breaks read as whitespace
- rewriting_breaks(): decorator for a function that returns the text rewritten (a redaction); the breaks are read as
  whitespace while it runs and put back in what it returns

[POS]
Companion of the leak detector's public functions. Only a text that starts with a JSON value is read this way, and only
that value: anywhere else a backslash and an ``n`` are two characters of the text (a Windows path, a password), and
reading them as a break would cut a secret that holds them. An escaped backslash is taken whole (``\\\\n`` is a
backslash and an ``n``, not a break), and a text that already holds a stand-in character is left as it is, so the way
back never turns a character of the text into a break.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from functools import wraps

# Whitespace to ``\s`` that does not turn up in tool output: the ASCII file, group and record separators.
_STAND_INS = {"\\n": "\x1c", "\\r": "\x1d", "\\t": "\x1e"}
_ESCAPE_RE = re.compile(r"\\[\\nrt]")
_JSON_STARTS = ("{", "[", '"')
_DECODER = json.JSONDecoder()


def _json_length(content: str) -> int:
    """The length of the JSON value the text starts with (blanks in front count), 0 when it starts with none."""
    start = 0
    while start < len(content) and content[start] in " \t\r\n":
        start += 1
    if content[start : start + 1] not in _JSON_STARTS:
        return 0
    try:
        return _DECODER.raw_decode(content, start)[1]
    except (ValueError, RecursionError):
        return 0


def _read_as_whitespace(content: str) -> str | None:
    """``content`` with each break escaped in its leading JSON value replaced by its stand-in, or None when there is none."""
    if "\\" not in content or any(stand_in in content for stand_in in _STAND_INS.values()):
        return None
    end = _json_length(content)
    if end == 0:
        return None
    value = content[:end]
    view = _ESCAPE_RE.sub(lambda match: _STAND_INS.get(match.group(0), match.group(0)), value)
    return None if view == value else view + content[end:]


def _put_back(text: str) -> str:
    for escape, stand_in in _STAND_INS.items():
        text = text.replace(stand_in, escape)
    return text


def reading_breaks[R](read: Callable[[str], R]) -> Callable[[str], R]:
    """``read`` run on the text with each escaped line break read as whitespace."""

    @wraps(read)
    def wrapper(content: str) -> R:
        return read(_read_as_whitespace(content) or content)

    return wrapper


def rewriting_breaks(rewrite: Callable[[str], str]) -> Callable[[str], str]:
    """``rewrite`` run on the text with each escaped line break read as whitespace; the breaks are put back after."""

    @wraps(rewrite)
    def wrapper(content: str) -> str:
        view = _read_as_whitespace(content)
        return rewrite(content) if view is None else _put_back(rewrite(view))

    return wrapper
