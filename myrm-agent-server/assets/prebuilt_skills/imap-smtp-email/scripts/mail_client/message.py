"""Message decoding helpers for the imap-smtp-email skill script: MIME headers, dates, summaries, bodies.

[INPUT]
- email.message.Message objects parsed by the email_manager.py facade

[OUTPUT]
- decode_header: RFC 2047 header text as a plain string, spaced as RFC 2047 §6.2 reads it; a malformed encoded word is
  returned as written
- message_summary: uid, from, to, subject, date and message id of one message, each a plain string even when the header
  holds raw 8-bit bytes
- ascii_msg_ids: the ids of a Message-ID or References value that a header can carry; one with raw 8-bit bytes is left out
- attachment_filename: decoded file name of an attachment part from Content-Disposition or Content-Type, raw 8-bit or not
- extract_body: plain-text body, falling back to HTML; a charset Python does not know is read as UTF-8

[POS]
Pure message-parsing half of the email_manager.py facade; no network or process I/O. A message from the mailbox is
untrusted, so one that declares a charset Python does not know, carries a malformed encoded word or holds raw 8-bit
bytes in a header is still readable.
"""

from __future__ import annotations

import email.errors
import email.header
import email.message
import email.utils


def _to_text(raw: bytes, charset: str | None) -> str:
    """Decode *raw* as *charset*; a name Python has no codec for (``unknown-8bit``, one with a NUL) is read as UTF-8."""
    try:
        return raw.decode(charset or "utf-8", errors="replace")
    except (LookupError, ValueError):
        return raw.decode("utf-8", errors="replace")


def decode_header(raw: str | email.header.Header | None) -> str:
    """Decode an RFC 2047 header value; the parser hands over a ``Header`` instead of a ``str`` for raw 8-bit bytes."""
    if not raw:
        return ""
    try:
        parts = email.header.decode_header(raw)
    except email.errors.HeaderParseError:
        return str(raw)
    decoded: list[str] = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(_to_text(part, charset))
        else:
            decoded.append(part)
    # The text next to an encoded word keeps its own spaces, and the spaces between two encoded words are already gone.
    return "".join(decoded)


def ascii_msg_ids(raw: str | email.header.Header | None) -> str:
    """The ids of a Message-ID or References value that a header can carry; an id with raw 8-bit bytes is left out.

    A threading header holds ids, not encoded words (RFC 2047 §5), so an id the parser hands over as a ``Header`` would be
    written as an encoded word. A value that is plain ASCII is returned unchanged.
    """
    text = str(raw or "")
    return text if text.isascii() else " ".join(token for token in text.split() if token.isascii())


def attachment_filename(part: email.message.Message) -> str:
    """Decoded file name of an attachment part, ``attachment`` when it names none.

    The standard library reads a ``Header`` (raw 8-bit bytes) as replacement characters, so the two headers that can name
    a file are decoded into a fresh message first.
    """
    names = email.message.Message()
    for header in ("Content-Disposition", "Content-Type"):
        value = part.get(header)
        if value is not None:
            names[header] = decode_header(value) if isinstance(value, email.header.Header) else value
    return decode_header(names.get_filename() or "attachment")


def _parse_date(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        return parsed.isoformat()
    except Exception:
        return raw


def message_summary(msg: email.message.Message, uid: int) -> dict[str, object]:
    # str() because a header value with raw 8-bit bytes is a Header object, which json.dumps cannot write.
    return {
        "uid": uid,
        "from": decode_header(msg.get("From", "")),
        "to": decode_header(msg.get("To", "")),
        "subject": decode_header(msg.get("Subject", "")),
        "date": _parse_date(str(msg.get("Date", ""))),
        "message_id": str(msg.get("Message-ID", "")),
    }


def extract_body(msg: email.message.Message) -> str:
    if not msg.is_multipart():
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            return _to_text(payload, msg.get_content_charset())
        return ""

    text_body = ""
    html_body = ""
    for part in msg.walk():
        ct = part.get_content_type()
        disp = str(part.get("Content-Disposition", ""))
        if "attachment" in disp:
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            continue
        decoded = _to_text(payload, part.get_content_charset())
        if ct == "text/plain" and not text_body:
            text_body = decoded
        elif ct == "text/html" and not html_body:
            html_body = decoded

    return text_body or html_body
