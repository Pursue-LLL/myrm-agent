"""Shape of the stdout call markers an MCP PTC script prints

[INPUT]
- (none)

[OUTPUT]
- MARKER_PREFIX / MARKER_SUFFIX: Delimiters of ``__MCP_DATA__{nonce}{base64(json)}__END__{nonce}``.
- scrub_outside_markers: Apply a scrubber to everything except marker spans.
- scrub_marker_spans: Apply a scrubber to the marker spans only.

[POS]
The output scrubber treats the base64 payload of a marker as a JWT (it always starts
with ``eyJ``, the encoding of ``{"``) and truncates it, which destroys every marker
before the host can read it. The scrubber and the host-side extractor therefore share
this one definition of what a marker looks like. Only the *shape* is known here: the
nonce that authenticates a marker lives in the agent layer, so the exemption cannot
depend on it. Spans the host does not authenticate are scrubbed after extraction
(``scrub_marker_spans``), so the exemption never lets text through unscrubbed.
"""

import re
from collections.abc import Callable

MARKER_PREFIX = "__MCP_DATA__"
MARKER_SUFFIX = "__END__"

_NONCE = r"[0-9a-f]{32}"
"""``secrets.token_hex(16)``, the nonce the IPC server mints per process."""

_MARKER_SHAPE = re.compile(rf"{MARKER_PREFIX}{_NONCE}[A-Za-z0-9+/=]*{MARKER_SUFFIX}{_NONCE}")


def scrub_outside_markers(text: str, scrub: Callable[[str], str]) -> str:
    """Scrub ``text`` but let marker-shaped spans through verbatim."""
    if MARKER_PREFIX not in text:
        return scrub(text)
    parts: list[str] = []
    cursor = 0
    for span in _MARKER_SHAPE.finditer(text):
        parts.append(scrub(text[cursor : span.start()]))
        parts.append(span.group(0))
        cursor = span.end()
    parts.append(scrub(text[cursor:]))
    return "".join(parts)


def scrub_marker_spans(text: str, scrub: Callable[[str], str]) -> str:
    """Scrub only the marker-shaped spans left in ``text``."""
    if MARKER_PREFIX not in text:
        return text
    return _MARKER_SHAPE.sub(lambda span: scrub(span.group(0)), text)
