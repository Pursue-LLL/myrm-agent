"""Untrusted file and directory names as text a model may be shown.

A name read from a workspace is third-party text: the repository's author chose it, and it can hold a line break, so a line of its own in a
system message. The injection scans read file contents and never see it.

[INPUT]
- core.security.detection.content_boundary::sanitize, detect_suspicious, strip_invisible_unicode (POS: untrusted-text neutralisation)

[OUTPUT]
- neutralize_name: one short line of plain text for a name; an ordinary name comes back unchanged

[POS]
The one place that turns a name taken from a workspace into prompt text. Line breaks, control and bidirectional characters become spaces,
framing markers are neutralised, a name that reads as an instruction is withheld, and a long name is cut.
"""

from __future__ import annotations

import re

from myrm_agent_harness.core.security.detection.content_boundary import (
    detect_suspicious,
    sanitize,
    strip_invisible_unicode,
)

_MAX_NAME_CHARS = 80
_LINE_BREAKS_AND_CONTROLS = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069]")
_WITHHELD_NAME = "[name withheld]"


def neutralize_name(name: str) -> str:
    """The name as it may appear in the prompt; an ordinary name comes back unchanged."""
    cleaned = sanitize(_LINE_BREAKS_AND_CONTROLS.sub(" ", strip_invisible_unicode(name)))
    if detect_suspicious(cleaned):
        return _WITHHELD_NAME
    if len(cleaned) > _MAX_NAME_CHARS:
        return cleaned[:_MAX_NAME_CHARS] + "..."
    return cleaned
