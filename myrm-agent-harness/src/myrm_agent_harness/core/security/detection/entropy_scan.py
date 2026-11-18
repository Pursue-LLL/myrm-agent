"""High-entropy token scan for credentials that carry no vendor prefix and no label.

[INPUT]
- core.security.detection.secret_value::is_reference_token (POS: shared rules telling a secret from a reference to one:
    identifiers, class names, constants, slugs, domains, query strings.)

[OUTPUT]
- find_high_entropy(): spans of the random-looking tokens in free text
- redact_high_entropy(): the text with each of those tokens replaced where the scan found it
- shannon_entropy(): Shannon entropy of a string in bits per character

[POS]
Unknown-credential tier of the leak detector. Splits text into tokens (URLs, UUIDs, long hex digests and file paths
removed first) and keeps those that are long, ASCII, alphanumeric with both letters and digits, not base64/hex blobs,
not a reference to a secret and above the entropy threshold. A token is reported and replaced by position: the same
characters inside a skipped path or URL are not the token the scan found.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable

from myrm_agent_harness.core.security.detection.secret_value import is_reference_token

_ENTROPY_MIN_TOKEN_LEN = 24
_ENTROPY_THRESHOLD = 4.2

_URL_STRIP_RE = re.compile(r"https?://\S+")
_UUID_STRIP_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_HEX_HASH_RE = re.compile(r"\b[0-9a-f]{40,}\b")
_FILE_PATH_RE = re.compile(r"(?:/[\w._-]+){2,}")
_SKIPPED_RES = (_URL_STRIP_RE, _UUID_STRIP_RE, _HEX_HASH_RE, _FILE_PATH_RE)
_TOKEN_RE = re.compile(r"[^\s,;:\"'`()\[\]{}|<>#]+")


def shannon_entropy(s: str) -> float:
    """Compute Shannon entropy in bits per character."""
    if not s:
        return 0.0
    freq = Counter(s.encode())
    length = len(s)
    return -sum((c / length) * math.log2(c / length) for c in freq.values())


def _is_all_hex(s: str) -> bool:
    return all(c in "0123456789abcdef" for c in s.lower())


def _looks_like_base64(s: str) -> bool:
    base64_special = set("+/=")
    return any(c in base64_special for c in s) and all(
        c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=" for c in s
    )


def _blank(match: re.Match[str]) -> str:
    """As many blanks as the skipped text had, so a token found after it keeps its offsets in the original text."""
    return " " * len(match.group(0))


def _is_random_token(token: str, already_matched: set[str]) -> bool:
    if len(token) < _ENTROPY_MIN_TOKEN_LEN or not token.isascii():
        return False
    if _is_all_hex(token) or _looks_like_base64(token):
        return False
    if not (any(c.isalpha() for c in token) and any(c.isdigit() for c in token)):
        return False
    if is_reference_token(token, min_length=_ENTROPY_MIN_TOKEN_LEN):
        return False
    if any(token in matched for matched in already_matched):
        return False
    return shannon_entropy(token) >= _ENTROPY_THRESHOLD


def find_high_entropy(content: str, already_matched: set[str]) -> list[tuple[int, int]]:
    """Spans (start, end) of the high-entropy tokens that may be unknown credentials.

    Skips tokens contained in a string of ``already_matched`` (matches of the other tiers).
    """
    stripped = content
    for pattern in _SKIPPED_RES:
        stripped = pattern.sub(_blank, stripped)
    return [m.span() for m in _TOKEN_RE.finditer(stripped) if _is_random_token(m.group(0), already_matched)]


def redact_high_entropy(content: str, already_matched: set[str], redact: Callable[[str], str]) -> str:
    """``content`` with each token ``find_high_entropy`` finds replaced by ``redact(token)``.

    The replacement is by position. The same characters can also stand inside a path or URL the scan skipped (a chat id
    in ``.context/<chat>/evicted/x.txt`` and as a value of its own); replacing the first occurrence in the text would
    rewrite the path and leave the token itself readable.
    """
    pieces: list[str] = []
    last = 0
    for start, end in find_high_entropy(content, already_matched):
        pieces += (content[last:start], redact(content[start:end]))
        last = end
    return "".join((*pieces, content[last:])) if pieces else content
