"""Message decoding helpers for the imap-smtp-email skill script: MIME headers, dates, summaries, bodies.

[INPUT]
- email.message.Message objects parsed by the email_manager.py facade

[OUTPUT]
- decode_header: RFC 2047 header text as a plain string, spaced as RFC 2047 §6.2 reads it; a malformed encoded word is
  returned as written
- message_summary: uid, from, to, subject, date and message id of one message, each a plain string even when the header
  holds raw 8-bit bytes
- ascii_msg_ids: the ids of a Message-ID or References value that a header can carry; one with raw 8-bit bytes is left out
- attachment_filename: decoded file name of an attachment part from Content-Disposition or Content-Type, raw 8-bit or not;
  ``attachment`` when it names none, an encoded word that decodes to nothing included
- attachment_parts: the parts the sender attached, in order: a disposition of ``attachment`` in any case, or a file that is
  not text and names itself, whether its disposition is ``inline`` or the name is only in Content-Type; a text part that
  names itself stays the body, so does a part the HTML points at with a ``cid:`` URL unless it is attached by its
  disposition, and a message that is one attachment is its own part
- attachment_bytes: what to save of an attachment part: its decoded content, an attached message/rfc822 with each header as
  the parser read it and CRLF line breaks, or none for a part that holds no file or an attached message the generator cannot write
- reply_recipients: where a reply goes, every Reply-To address or, when Reply-To holds none, every From address, comma
  separated; empty when neither holds one
- extract_body: plain-text body, falling back to HTML, never an attachment; a charset Python does not know is read as UTF-8

[POS]
Pure message-parsing half of the email_manager.py facade; no network or process I/O. A message from the mailbox is
untrusted, so one that declares a charset Python does not know, carries a malformed encoded word or holds raw 8-bit
bytes in a header is still readable.
"""

from __future__ import annotations

import email.errors
import email.header
import email.message
import email.policy
import email.utils
import re
import urllib.parse
from collections.abc import Iterator


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


def _name_headers(part: email.message.Message) -> email.message.Message:
    """A fresh message holding the two headers that can name a file or call a part an attachment.

    The standard library reads a ``Header`` (raw 8-bit bytes) as replacement characters, so such a value is decoded first.
    """
    headers = email.message.Message()
    for header in ("Content-Disposition", "Content-Type"):
        value = part.get(header)
        if value is not None:
            headers[header] = decode_header(value) if isinstance(value, email.header.Header) else value
    return headers


def attachment_filename(part: email.message.Message) -> str:
    """Decoded file name of an attachment part, ``attachment`` when it names none or its name decodes to nothing."""
    return decode_header(_name_headers(part).get_filename() or "") or "attachment"


# A cid: URL names the part it embeds by Content-ID (RFC 2392); the id ends at whitespace, a quote, a bracket or a parenthesis.
_CID_URL = re.compile(r"cid:([^\s\"'<>()]+)", re.IGNORECASE)


def _embedded_ids(msg: email.message.Message) -> frozenset[str]:
    """The Content-IDs that the HTML parts of *msg* point at with a ``cid:`` URL, as written and with ``%`` escapes decoded.

    RFC 2392 decodes the escapes of the URL to get the Content-ID, but its own example writes the id with the escape kept,
    so both forms are kept.
    """
    ids: set[str] = set()
    for part in msg.walk():
        payload = part.get_payload(decode=True) if part.get_content_type() == "text/html" else None
        if isinstance(payload, bytes):
            for found in _CID_URL.findall(_to_text(payload, part.get_content_charset())):
                ids.update((found, urllib.parse.unquote(found)))
    return frozenset(ids)


def _is_attachment(part: email.message.Message, embedded: frozenset[str] = frozenset()) -> bool:
    """Whether the sender attached *part*, however it is written, rather than the HTML body embedding it through *embedded*.

    The disposition type is case-insensitive (RFC 2183 §2). A part that is not text and names a file counts whether its
    disposition is ``inline`` or absent; a text part that names itself is the body, and so is a part that the HTML points
    at by Content-ID. A disposition of ``attachment`` always counts.
    """
    headers = _name_headers(part)
    if headers.get_content_disposition() == "attachment":
        return True
    content_id = decode_header(part.get("Content-ID")).strip().removeprefix("<").removesuffix(">")
    return (
        headers.get_content_maintype() not in ("text", "multipart")
        and bool(headers.get_filename())
        and content_id not in embedded
    )


def attachment_parts(msg: email.message.Message) -> Iterator[email.message.Message]:
    """The parts of *msg* that the sender attached, in order; a message that is one attachment is its own part."""
    embedded = _embedded_ids(msg)
    return (part for part in msg.walk() if _is_attachment(part, embedded))


_LINE_BREAK = re.compile(r"\r\n|\r|\n")


class _AsReceivedPolicy(email.policy.Compat32):
    """Writes each header as the parser stored it, with the line breaks inside a value changed to the policy's.

    The stock policies fold a header at a vertical tab, a form feed or a file, group or record separator on some
    interpreters, which cuts the header or makes the generator refuse it, so a header is never folded here. Raw 8-bit
    bytes in a value, which the parser holds as surrogate escapes, are written back as the bytes they were.
    """

    def fold_binary(self, name: str, value: str) -> bytes:
        text = self.linesep.join(_LINE_BREAK.split(value))
        return f"{name}: {text}{self.linesep}".encode("utf-8", "surrogateescape")


_AS_RECEIVED = _AsReceivedPolicy(linesep="\r\n")


def attachment_bytes(part: email.message.Message) -> bytes | None:
    """What to save of an attachment part: its decoded content, or an attached message written out with its headers as read.

    A part that holds no file, such as a container, has none. So has an attached message the generator cannot write,
    one nested so deep that it runs out of stack or one it refuses; such a message is left out rather than saved in
    another form. ``_AS_RECEIVED`` writes each header as the parser read it (the blanks after the colon, which the parser
    drops, become one space) and ends the lines of the headers and of a text body in CRLF.
    """
    content = part.get_payload(decode=True)
    if isinstance(content, bytes):
        return content
    payload = part.get_payload()
    attached = payload[0] if part.get_content_type() == "message/rfc822" and isinstance(payload, list) else None
    if not isinstance(attached, email.message.Message):
        return None
    try:
        return attached.as_bytes(policy=_AS_RECEIVED)
    except (email.errors.MessageError, RecursionError):
        return None


def reply_recipients(original: email.message.Message) -> str:
    """The addresses a reply to *original* goes to, comma separated: all of its Reply-To, or all of its From when Reply-To
    holds none; empty if neither does.

    ``parseaddr`` reads one address and returns none for a list, so the header is read with ``getaddresses``, which also
    takes the ``Header`` object the parser returns for a value with raw 8-bit bytes.
    """
    for header in ("Reply-To", "From"):
        addresses = [address for _, address in email.utils.getaddresses([original.get(header, "")]) if address]
        if addresses:
            return ", ".join(addresses)
    return ""


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
        if isinstance(payload, bytes) and not _is_attachment(msg):
            return _to_text(payload, msg.get_content_charset())
        return ""

    text_body = ""
    html_body = ""
    for part in msg.walk():
        ct = part.get_content_type()
        if _is_attachment(part):
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
