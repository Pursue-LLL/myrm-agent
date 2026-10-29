"""Header redaction rules: API-key style headers and Cookie / Set-Cookie header lines.

[INPUT]
- bounded_replace::_replace_pattern_bounded (POS: Bounded regex replacement, the ReDoS guard of every redaction pass)
- masking::_mask_token (POS: Leaf value-masking helpers of the runtime redactor)

[OUTPUT]
- ``_SECRET_HEADER_RE`` — ``x-api-key: …`` style header or property, also read by ``agent/skills/security/content_sanitizer.py``
- ``_COOKIE_HEADER_LINE_RE`` / ``_COOKIE_HEADER_QUOTED_RE`` / ``_redact_cookie_header`` — cookie header lines and their replacer
- ``_redact_secret_headers(text)`` — the header pass of the redaction pipeline

[POS]
Header rules of the runtime redactor; ``engine.py`` runs ``_redact_secret_headers`` as one name-based pass.
"""

from __future__ import annotations

import re

from .bounded_replace import _replace_pattern_bounded
from .masking import _mask_token

# ── API-key 风格认证头 ──────────
_SECRET_HEADER_NAMES = r"(?:x-api-key|x-goog-api-key|api-key|apikey|x-api-token|x-auth-token|x-access-token)"
_SECRET_HEADER_RE = re.compile(rf"({_SECRET_HEADER_NAMES}\s*:\s*)(\S+)", re.IGNORECASE)

# Cookie / Set-Cookie header lines: the value is a `; `-separated list of cookies (the session among them) and is
# masked whole. A raw header line (`Cookie: a=1; b=2`, curl's `> Cookie:` / `< Set-Cookie:` trace lines) runs to the end
# of the line. The same header inside a JSON string or a dumped request (`b'GET / HTTP/1.1\r\nCookie: a=1\r\n'`) also
# stops at an escaped line break and at the quote that closes a JSON string, so the rest of the record stays intact.
# One inside a quoted command argument (`-H "Cookie: a=1"`) stops at the quote that opened it (and at the backslash
# that escapes it), which keeps the closing quote and the rest of the command. The name is not glued to a word, `-` or
# a quote on its left, so `X-Cookie:` and `NoCookie:` are other fields and `Cookie policy:` is prose; the one
# exception is the escaped line break of a dumped request. Group ``head`` is the header name and colon, the one part
# that stays.
_COOKIE_VALUE_END = r"""\\[rn]|"[,}\]]"""
_COOKIE_HEADER_LINE_RE = re.compile(
    rf"""(?:(?<![\w\-"'])|(?<=\\n))(?P<head>(?:Set-)?Cookie:[ \t]*)(?!{_COOKIE_VALUE_END})\S(?:(?!{_COOKIE_VALUE_END})[^\r\n])*""",
    re.IGNORECASE,
)
_COOKIE_HEADER_QUOTED_RE = re.compile(
    r"""(?<=(["']))(?P<head>(?:Set-)?Cookie:[ \t]*)(?!\\?\1)\S(?:(?!\\?\1)[^\r\n])*""",
    re.IGNORECASE,
)


def _redact_cookie_header(m: re.Match[str]) -> str:
    """Replacement for the cookie header patterns: keep the header name and colon, hide the whole value."""
    return f"{m['head']}***"


def _redact_secret_headers(text: str) -> str:
    """Mask the value of an API-key style header or property (``x-api-key: …``) and of a cookie header line."""
    text = _replace_pattern_bounded(text, _SECRET_HEADER_RE, lambda m: f"{m.group(1)}{_mask_token(m.group(2))}")
    text = _replace_pattern_bounded(text, _COOKIE_HEADER_LINE_RE, _redact_cookie_header)
    return _replace_pattern_bounded(text, _COOKIE_HEADER_QUOTED_RE, _redact_cookie_header)
