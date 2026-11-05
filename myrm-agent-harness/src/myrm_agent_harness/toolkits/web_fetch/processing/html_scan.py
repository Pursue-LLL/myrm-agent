"""Linear-time scans of raw HTML text.

[INPUT]
- (none)

[OUTPUT]
- extract_title: Text of the first <title> element
- strip_script_and_style: The page without its <script> and <style> blocks
- strip_tags: The text with every <...> tag removed
- body_content: The text between the opening <body> tag and the last </body>

[POS]
Text scans behind the anti-bot checks and the page title. A fetched page is untrusted, so each scan visits every
character a bounded number of times. The equivalent single regexes (``<title[^>]*>(.*?)</title>``,
``<script\\b[\\s\\S]*?</script>``) rescan the rest of the page for every opener that is never closed, which turns a
crafted page into minutes of CPU time.
"""

from __future__ import annotations

import re

_TITLE_OPEN = re.compile(r"<title", re.IGNORECASE)
_TITLE_CLOSE = re.compile(r"</title>", re.IGNORECASE)
_BODY_OPEN = re.compile(r"<body\b", re.IGNORECASE)
_BODY_CLOSE = re.compile(r"</body>", re.IGNORECASE)
_SCRIPT_BLOCK = (re.compile(r"<script\b", re.IGNORECASE), re.compile(r"</script>", re.IGNORECASE))
_STYLE_BLOCK = (re.compile(r"<style\b", re.IGNORECASE), re.compile(r"</style>", re.IGNORECASE))


def extract_title(html: str) -> str | None:
    """Return the text of the first ``<title>`` element, or None when the page has no closed one."""
    opening = _TITLE_OPEN.search(html)
    if opening is None:
        return None
    tag_end = html.find(">", opening.end())
    if tag_end < 0:
        return None
    closing = _TITLE_CLOSE.search(html, tag_end + 1)
    return None if closing is None else html[tag_end + 1 : closing.start()]


def body_content(html: str) -> str | None:
    """Return the text between the first ``<body ...>`` tag and the last ``</body>``, or None when either is missing."""
    opening = _BODY_OPEN.search(html)
    if opening is None:
        return None
    tag_end = html.find(">", opening.end())
    if tag_end < 0:
        return None
    last_close = -1
    for closing in _BODY_CLOSE.finditer(html, tag_end + 1):
        last_close = closing.start()
    return None if last_close < 0 else html[tag_end + 1 : last_close]


def strip_script_and_style(html: str) -> str:
    """Remove every ``<script>...</script>`` block, then every ``<style>...</style>`` block."""
    return _strip_blocks(_strip_blocks(html, _SCRIPT_BLOCK), _STYLE_BLOCK)


def strip_tags(text: str) -> str:
    """Remove every ``<...>`` sequence that holds at least one character; ``<>`` stays."""
    parts: list[str] = []
    pos = 0
    while (tag_start := text.find("<", pos)) >= 0:
        tag_end = text.find(">", tag_start + 1)
        if tag_end < 0:
            break
        if tag_end == tag_start + 1:
            parts.append(text[pos : tag_start + 1])
            pos = tag_start + 1
            continue
        parts.append(text[pos:tag_start])
        pos = tag_end + 1
    parts.append(text[pos:])
    return "".join(parts)


def _strip_blocks(html: str, block: tuple[re.Pattern[str], re.Pattern[str]]) -> str:
    """Remove every block that runs from an opener to the next closer; an opener without a closer is kept."""
    opener, closer = block
    parts: list[str] = []
    pos = 0
    while (start := opener.search(html, pos)) is not None:
        end = closer.search(html, start.end())
        if end is None:
            break
        parts.append(html[pos : start.start()])
        pos = end.end()
    parts.append(html[pos:])
    return "".join(parts)
