"""Message decoding helpers for the imap-smtp-email skill script: MIME headers, dates, summaries, bodies.

[INPUT]
- email.message.Message objects parsed by the email_manager.py facade

[OUTPUT]
- decode_header: RFC 2047 header text as a plain string; a malformed encoded word is returned as written
- message_summary: uid, from, to, subject, date and message id of one message
- extract_body: plain-text body, falling back to HTML; a charset Python does not know is read as UTF-8

[POS]
Pure message-parsing half of the email_manager.py facade; no network or process I/O. A message from the mailbox is
untrusted, so one that declares a charset Python does not know or carries a malformed encoded word is still readable.
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


def decode_header(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        parts = email.header.decode_header(raw)
    except email.errors.HeaderParseError:
        return raw
    decoded: list[str] = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(_to_text(part, charset))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _parse_date(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        return parsed.isoformat()
    except Exception:
        return raw


def message_summary(msg: email.message.Message, uid: int) -> dict[str, object]:
    return {
        "uid": uid,
        "from": decode_header(msg.get("From", "")),
        "to": decode_header(msg.get("To", "")),
        "subject": decode_header(msg.get("Subject", "")),
        "date": _parse_date(msg.get("Date")),
        "message_id": msg.get("Message-ID", ""),
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
