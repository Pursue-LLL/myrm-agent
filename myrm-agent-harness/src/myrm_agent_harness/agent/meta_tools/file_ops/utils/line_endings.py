"""Line ending detection and normalization utilities.

Preserves the original line ending style (LF / CRLF) of a file across
edits performed by the agent. Agent tool parameters arrive via JSON which
does not transmit `\\r` (RFC 8259 §7), so without explicit normalization
every edit on a CRLF file introduces mixed line endings.

[INPUT]
- (none)

[OUTPUT]
- strip_utf8_bom: function — Drop a leading UTF-8 BOM from displayed text
- detect_line_ending: function — Detect dominant line ending
- normalize_line_endings: function — Convert all line endings to target
- view_lines: function — The lines a view shows for text split on LF: CRLF and a bare CR end a line too

[POS]
Line-ending rules shared by the edit pipeline (match on LF text, write the file's own endings back) and the view
(show lines, whatever ends them).
"""

from __future__ import annotations

_SAMPLE_SIZE = 4096

_UTF8_BOM = "\ufeff"


def strip_utf8_bom(text: str) -> str:
    """Strip a leading UTF-8 BOM (``\\ufeff``) from *text* if present.

    A UTF-8 BOM appears as ``\\ufeff`` at the start of text decoded from a file
    written by Windows editors. It is invisible but pollutes the first line's
    content and can break exact-match tools (e.g. str_replace SEARCH). Stripping
    it on read is a display-layer concern; the file on disk is untouched.
    """
    if text.startswith(_UTF8_BOM):
        return text[1:]
    return text


def detect_line_ending(content: str) -> str | None:
    """Return the dominant line ending in *content*, or ``None`` if undetermined.

    Scans the first 4 KiB — enough to decide, cheap to scan.
    Returns ``"\\r\\n"`` when any CRLF is present, ``"\\n"`` for pure-LF,
    or ``None`` for single-line / empty content where the style is ambiguous.
    """
    if not content:
        return None
    head = content[:_SAMPLE_SIZE]
    if "\r\n" in head:
        return "\r\n"
    if "\n" in head:
        return "\n"
    return None


def normalize_line_endings(text: str, target: str) -> str:
    """Convert all line endings in *text* to *target* (``"\\n"`` or ``"\\r\\n"``).

    Idempotent: applying the same target twice yields identical output.
    Handles mixed endings (lone ``\\r``, mixed CRLF/LF) in a single pass.
    """
    # Collapse everything to LF first (CRLF → LF, lone CR → LF)
    lf_only = text.replace("\r\n", "\n").replace("\r", "\n")
    if target == "\r\n":
        return lf_only.replace("\n", "\r\n")
    return lf_only


def view_lines(raw_lines: list[str]) -> list[str]:
    """The lines a view shows for text that was split on ``\\n``; always a new list.

    A line ends with ``\\n``, ``\\r\\n`` or a bare ``\\r``, as in the universal-newline reading ``preview`` and ``stream``
    use, so the same text shows the same lines whatever ends them. Only the view does this: the integrity hash and the
    edit pipeline keep working on the raw text, whose endings are written back as they were.
    """
    text = "\n".join(raw_lines)
    if "\r" not in text:
        return list(raw_lines)
    return normalize_line_endings(text, "\n").split("\n")
