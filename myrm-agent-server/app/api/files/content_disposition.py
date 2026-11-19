"""[INPUT]
- a disposition type (``inline`` / ``attachment``) and any client- or filesystem-supplied file name

[OUTPUT]
- build_content_disposition: a header value that is always latin-1 encodable

[POS]
Shared by the download endpoints (storage and workspace browse). Header values travel as latin-1, so a
raw non-latin-1 name makes the response constructor raise and the whole download a 500.
"""

from __future__ import annotations

import unicodedata
from urllib.parse import quote

_FALLBACK_NAME = "file"


def build_content_disposition(disposition: str, filename: str) -> str:
    """Build ``Content-Disposition`` for ``filename``, whatever characters it holds.

    Control characters are dropped (CR/LF would inject headers). The plain ``filename`` is an ASCII
    fallback for old clients, and RFC 5987 ``filename*`` carries the real name. A lone surrogate,
    which a UTF-8 encoder rejects, becomes ``?``.
    """
    cleaned = "".join(ch for ch in filename if unicodedata.category(ch) != "Cc") or _FALLBACK_NAME
    ascii_name = "".join(ch if ch.isascii() else "_" for ch in cleaned)
    fallback = ascii_name.replace("\\", "\\\\").replace('"', '\\"')
    encoded = quote(cleaned.encode("utf-8", "replace"), safe="")
    return f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"
