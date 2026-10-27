"""The answer for a response body too long to read inline: its start, and a masked copy kept in the vault.

[INPUT]
- core.security.redact::redact_sensitive_text (POS: credential masking, applied before a body is cut or stored)
- session.browser_session_extraction_mixin::ContentVault (POS: minimal vault protocol; `put` gives a `vault://` pointer)

[OUTPUT]
- BODY_PREVIEW_MAX_CHARS: the longest body answered inline, and how much of a longer one the answer shows
- VAULT_COPY_MAX_CHARS: how much of a body the vault copy keeps
- wrap_long_lines: a text with every line longer than a width cut into lines of at most that width
- long_body_answer: the pointer-first answer for a body longer than BODY_PREVIEW_MAX_CHARS

[POS]
Keeps response-body shaping out of `intelligence.py`. A body that does not fit inline is masked as a whole first and cut
afterwards (the preview) or wrapped into short lines (the vault copy), so a credential the cut would split leaves no
fragment, and a minified body that is a single line can still be read by line range through `file_read`.
The copy is bounded because masking costs up to a few microseconds per character (4.6 s per million characters in the
slowest of 20 adversarial shapes measured). It runs in a worker thread, which keeps the event loop's longest stall near
0.2 s where an inline run would hold it for the whole masking time. Without a vault, or when the vault refuses the
write, the answer is the preview and the body's length.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, NamedTuple

from myrm_agent_harness.core.security.redact import redact_sensitive_text

if TYPE_CHECKING:
    from ..browser_session_extraction_mixin import ContentVault

logger = logging.getLogger(__name__)

BODY_PREVIEW_MAX_CHARS = 8000
VAULT_COPY_MAX_CHARS = 1_000_000
# Without a vault only the preview is made, so only a window a little wider than it is masked.
_PREVIEW_RAW_WINDOW = 16384
# Masking runs this far past the copy's end before the cut, so a credential the cut would split stays masked:
# a PEM private key, the longest thing the masker matches, is 1,704 characters for RSA-2048 and 3,272 for RSA-4096.
_CUT_MARGIN = 4096
_LINE_WIDTH = 200


def wrap_long_lines(text: str, width: int = _LINE_WIDTH) -> str:
    """Cut every line longer than `width` into lines of at most `width` characters.

    A line is what file_read counts: text between newlines (not `str.splitlines`, which also breaks on U+2028 and
    others), so the line numbers of the copy are the ones file_read prints.
    """
    lines: list[str] = []
    for line in text.split("\n"):
        if len(line) <= width:
            lines.append(line)
        else:
            lines.extend(line[start : start + width] for start in range(0, len(line), width))
    return "\n".join(lines)


class _MaskedBody(NamedTuple):
    """What masking a body produced: its preview, where its copy is (None: not stored), and what the copy holds."""

    preview: str
    pointer: str | None
    copied_chars: int
    whole: bool


def _mask_and_store(vault: ContentVault, body: str, filename: str, description: str) -> _MaskedBody:
    """Mask `body` and keep its first VAULT_COPY_MAX_CHARS masked chars, wrapped, in the vault.

    Masking can lengthen a text (a short secret becomes `***`) as well as shorten it, so whether the copy holds the
    whole body is decided on the masked length, not on the body's.
    """
    window = body[: VAULT_COPY_MAX_CHARS + _CUT_MARGIN]
    masked = redact_sensitive_text(window)
    copy = masked[:VAULT_COPY_MAX_CHARS]
    preview = copy[:BODY_PREVIEW_MAX_CHARS]
    try:
        pointer = vault.put(wrap_long_lines(copy), filename, content_type="text/plain", description=description)
    except Exception as exc:
        logger.warning("Network response body not saved to the vault: %s", exc)
        return _MaskedBody(preview, None, 0, False)
    return _MaskedBody(preview, pointer, len(copy), len(window) == len(body) and len(copy) == len(masked))


def _head_only_answer(preview: str, total: int, mime: str) -> str:
    return f"{preview}\n\n... [truncated, total {total} chars] MIME: {mime}"


async def long_body_answer(
    body: str, mime_type: str | None, *, vault: ContentVault | None, filename: str, description: str
) -> str:
    """The answer for `body`, which is longer than BODY_PREVIEW_MAX_CHARS: where all of it is, then its start.

    Args:
        body: the response body text, not yet masked
        mime_type: the response's MIME type (None or empty when unknown)
        vault: where the copy goes; None answers with the preview alone
        filename: the copy's name in the vault
        description: what the vault records about the copy (must not carry credentials)
    """
    total = len(body)
    mime = mime_type or "unknown"
    if vault is None:
        return _head_only_answer(
            redact_sensitive_text(body[:_PREVIEW_RAW_WINDOW])[:BODY_PREVIEW_MAX_CHARS], total, mime
        )
    masked = await asyncio.to_thread(_mask_and_store, vault, body, filename, description)
    if masked.pointer is None:
        return _head_only_answer(masked.preview, total, mime)
    saved = (
        f"saved in full to {masked.pointer}"
        if masked.whole
        else f"the first {masked.copied_chars} saved to {masked.pointer}"
    )
    return (
        f"[Response body: {total} chars, {saved} (read it with file_read; lines wrapped at {_LINE_WIDTH} chars). "
        f"MIME: {mime}. First {BODY_PREVIEW_MAX_CHARS} chars:]\n{masked.preview}"
    )
