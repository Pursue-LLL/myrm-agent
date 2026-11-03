"""Email inbound: RFC 822 message to InboundMessage conversion.

Handles multipart bodies, HTML-to-Markdown cleaning, attachment extraction, thread headers,
automated-sender filtering and forwarded-message parsing (MIME message/rfc822, subject prefix, body separator).

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class; supplies the host members the mixin calls)
- channels.providers.email.forward::FWD_SUBJECT_PREFIXES, parse_forwarded_body (POS: forwarded email parsing)
- channels.types::InboundMessage, MediaAttachment, MediaType (POS: channel message value types)

[OUTPUT]
- EmailInboundMixin: _parse_email used by EmailChannel's IMAP poller

[POS]
Inbound half of EmailChannel. The host owns IMAP/SMTP connectivity and polling; the mixin only converts a raw
RFC 822 message into an InboundMessage. Headers, bodies and attachments are read as the sender wrote them: raw UTF-8
headers (RFC 6532), a charset name Python has no codec for and a cut-off encoded word are decoded instead of failing the
message; a part is an attachment however its disposition is spelled or when only its Content-Type names it, and a message
that is one attachment is attached rather than read as text. The sender chooses the file name, so only a plain extension
of it reaches the path an attachment is saved under. The files of a message are written once the rest of it has been
read, all of them or none, because a message that fails is read again.
"""

from __future__ import annotations

import email as email_lib
import email.errors
import email.header
import email.utils
import logging
import re
import tempfile
import urllib.parse
from collections.abc import Sequence
from email.message import Message
from pathlib import Path

from app.channels.core.base import BaseChannel
from app.channels.types import (
    InboundMessage,
    MediaAttachment,
    MediaType,
)

from .forward import (
    FWD_SUBJECT_PREFIXES,
    parse_forwarded_body,
)

logger = logging.getLogger(__name__)

_NOREPLY_PATTERNS = (
    "noreply",
    "no-reply",
    "no_reply",
    "donotreply",
    "do-not-reply",
    "mailer-daemon",
    "postmaster",
    "bounce",
    "notifications@",
    "automated@",
    "auto-confirm",
    "auto-reply",
    "automailer",
)

_AUTOMATED_HEADERS: dict[str, str] = {
    "Auto-Submitted": "no",
    "Precedence": "bulk,list,junk",
    "X-Auto-Response-Suppress": "",
    "List-Unsubscribe": "",
}


def _to_text(raw: bytes, charset: str | None) -> str:
    """Decode *raw* as *charset*; a name Python has no codec for (``unknown-8bit``, ``x-unknown``) is read as UTF-8."""
    try:
        return raw.decode(charset or "utf-8", errors="replace")
    except (LookupError, ValueError):
        return raw.decode("utf-8", errors="replace")


def _decode_header(raw: str | email.header.Header) -> str:
    """A header value as plain text: RFC 2047 encoded words (=?UTF-8?B?...?=) are decoded; a value that carries raw 8-bit
    bytes is read as those bytes, and an encoded word inside it stays as written, as does one that is cut off."""
    try:
        parts = email.header.decode_header(raw)
    except email.errors.HeaderParseError:
        return str(raw)
    # The text beside an encoded word keeps its own spaces, and the spaces between two encoded words are already gone.
    return "".join(_to_text(part, charset) if isinstance(part, bytes) else part for part, charset in parts)


def _text(value: str | email.header.Header) -> str:
    """A header value as text, without decoding encoded words.

    The parser returns ``str`` for an ASCII header but an ``email.header.Header`` for raw UTF-8 bytes (RFC 6532), which
    neither ``parseaddr``, ``split`` nor JSON accept.
    """
    return value if isinstance(value, str) else _decode_header(value)


def _is_automated_sender(address: str, msg: Message) -> bool:
    """Detect automated/noreply senders to prevent reply loops."""
    addr = address.lower()
    if any(pat in addr for pat in _NOREPLY_PATTERNS):
        return True
    for hdr, reject_vals in _AUTOMATED_HEADERS.items():
        value = _text(msg.get(hdr, ""))
        if not value:
            continue
        if hdr == "Auto-Submitted":
            if value.strip().lower() != "no":
                return True
        elif hdr == "Precedence":
            if value.strip().lower() in reject_vals.split(","):
                return True
        else:
            return True
    return False


def _html_to_markdown(html: str) -> str:
    """Convert email HTML body to clean Markdown for LLM consumption."""
    if not html:
        return ""
    from myrm_agent_harness.toolkits.web_fetch.processing.html_to_markdown import HTML2Markdown

    converter = HTML2Markdown()
    converter.update_params(ignore_images=True)
    return converter.handle(html).strip()


# An attachment is saved with the extension of the sender's file name so that extraction can route by it, but only a plain
# one: the name is the sender's choice, and the extension ends up in a path, in prompts and in what the file system accepts.
_SAFE_SUFFIX = re.compile(r"\.[A-Za-z0-9]{1,16}")
# A ``cid:`` URL names the part it embeds by Content-ID (RFC 2392); the id ends at white space, a quote, a bracket or a parenthesis.
_CID_URL = re.compile(r"cid:([^\s\"'<>()]+)", re.IGNORECASE)


def _name_headers(part: Message) -> Message:
    """A fresh message holding the two headers that can name a file or call a part an attachment.

    The parser returns a ``Header`` for raw UTF-8 bytes (RFC 6532) and the standard library reads that as replacement
    characters, so such a value is decoded first.
    """
    headers = Message()
    for name in ("Content-Disposition", "Content-Type"):
        value = part.get(name)
        if value is not None:
            headers[name] = _text(value)
    return headers


def _embedded_ids(msg: Message) -> frozenset[str]:
    """The Content-IDs that the HTML parts of *msg* point at with a ``cid:`` URL, as written and with ``%`` escapes decoded.

    RFC 2392 decodes the escapes of the URL to get the Content-ID, but its own example writes the id with the escape
    kept, so both forms are kept.
    """
    ids: set[str] = set()
    for part in msg.walk():
        payload = part.get_payload(decode=True) if part.get_content_type() == "text/html" else None
        if isinstance(payload, bytes):
            for found in _CID_URL.findall(_to_text(payload, part.get_content_charset())):
                ids.update((found, urllib.parse.unquote(found)))
    return frozenset(ids)


def _is_attachment(part: Message, embedded: frozenset[str] = frozenset()) -> bool:
    """Whether the sender attached *part*, however it is written, rather than the HTML body embedding it through *embedded*.

    The disposition type is case-insensitive (RFC 2183 section 2). A part that is not text and names a file counts
    whether its disposition is ``inline`` or absent; a text part that names itself is the body, and so is a part that the
    HTML points at by Content-ID. A disposition of ``attachment`` always counts.
    """
    headers = _name_headers(part)
    if headers.get_content_disposition() == "attachment":
        return True
    content_id = _text(part.get("Content-ID", "")).strip().removeprefix("<").removesuffix(">")
    return (
        headers.get_content_maintype() not in ("text", "multipart")
        and bool(headers.get_filename())
        and content_id not in embedded
    )


def _attachment_filename(part: Message) -> str:
    """The decoded file name an attachment part gives itself, ``attachment`` when it names none or the name decodes to nothing."""
    return _decode_header(_name_headers(part).get_filename() or "") or "attachment"


def _safe_suffix(filename: str) -> str:
    """The extension of *filename* when it is plain, otherwise none."""
    suffix = Path(filename).suffix
    return suffix if _SAFE_SUFFIX.fullmatch(suffix) else ""


def _media_type(content_type: str) -> MediaType:
    if content_type.startswith("image/"):
        return MediaType.IMAGE
    if content_type.startswith("audio/"):
        return MediaType.AUDIO
    if content_type.startswith("video/"):
        return MediaType.VIDEO
    return MediaType.DOCUMENT


def _save_attachment(part: Message, content_type: str) -> MediaAttachment:
    """Describe an attachment *part* and save its payload to a temporary file; a file that could not be written is removed."""
    filename = _attachment_filename(part)
    file_data = part.get_payload(decode=True)
    saved_path: str | None = None
    if isinstance(file_data, bytes) and file_data:
        tmp = tempfile.NamedTemporaryFile(delete=False, prefix="email_att_", suffix=_safe_suffix(filename))
        try:
            with tmp:
                tmp.write(file_data)
        except OSError:
            Path(tmp.name).unlink(missing_ok=True)
            raise
        saved_path = tmp.name
    return MediaAttachment(media_type=_media_type(content_type), filename=filename, mime_type=content_type, path=saved_path)


def _save_attachments(parts: Sequence[tuple[Message, str]]) -> tuple[MediaAttachment, ...]:
    """Save every attachment of a message, or none: when one fails the message is read again and would write the rest twice."""
    saved: list[MediaAttachment] = []
    try:
        for part, content_type in parts:
            saved.append(_save_attachment(part, content_type))
    except Exception:
        for attachment in saved:
            if attachment.path:
                Path(attachment.path).unlink(missing_ok=True)
        raise
    return tuple(saved)


class EmailInboundMixin(BaseChannel):
    """Email inbound message parsing for ``EmailChannel``.

    Requires the host class to provide the attributes below plus ``_build_inbound`` from ``BaseChannel``.
    """

    _from_address: str

    def _parse_email(self, raw: bytes, uid: int) -> InboundMessage | None:
        msg = email_lib.message_from_bytes(raw)

        sender_email = email.utils.parseaddr(_text(msg.get("From", "")))[1]
        if not sender_email or sender_email == self._from_address:
            return None
        if _is_automated_sender(sender_email, msg):
            logger.debug("Email: skipping automated sender %s", sender_email)
            return None

        subject = _decode_header(msg.get("Subject", ""))
        message_id = _text(msg.get("Message-ID", ""))
        in_reply_to = _text(msg.get("In-Reply-To", ""))
        references = _text(msg.get("References", ""))

        text_body = ""
        html_body = ""
        attachments: list[tuple[Message, str]] = []
        forwarded_rfc822: Message | None = None

        if msg.is_multipart():
            embedded = _embedded_ids(msg)
            for part in msg.walk():
                ct = part.get_content_type()

                if ct == "message/rfc822":
                    payload = part.get_payload()
                    if isinstance(payload, list) and payload and isinstance(payload[0], Message):
                        forwarded_rfc822 = payload[0]
                    continue

                if _is_attachment(part, embedded):
                    attachments.append((part, ct))
                elif ct == "text/html":
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        html_body = _to_text(payload, part.get_content_charset())
                elif ct == "text/plain" and not text_body:
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        text_body = _to_text(payload, part.get_content_charset())
        elif msg.get_content_maintype() != "text" and _is_attachment(msg):
            # The message is itself the attachment; a single text part stays the body whatever its disposition says.
            attachments.append((msg, msg.get_content_type()))
        else:
            payload = msg.get_payload(decode=True)
            if isinstance(payload, bytes):
                decoded = _to_text(payload, msg.get_content_charset())
                if msg.get_content_type() == "text/html":
                    html_body = decoded
                else:
                    text_body = decoded

        body = text_body or _html_to_markdown(html_body)

        if not body.strip() and not attachments:
            return None

        thread_id = in_reply_to or (references.split()[-1] if references else None)

        metadata: dict[str, object] = {
            "subject": subject,
            "message_id": message_id,
            "uid": uid,
        }

        is_forwarded = bool(subject.lower().startswith(FWD_SUBJECT_PREFIXES))

        content = body.strip()

        if forwarded_rfc822 is not None:
            is_forwarded = True
            fwd_from = email.utils.parseaddr(_text(forwarded_rfc822.get("From", "")))[1]
            fwd_subject = _decode_header(forwarded_rfc822.get("Subject", ""))
            fwd_date = _text(forwarded_rfc822.get("Date", ""))
            fwd_body = ""
            if forwarded_rfc822.is_multipart():
                fwd_text = ""
                fwd_html = ""
                for sub in forwarded_rfc822.walk():
                    sub_ct = sub.get_content_type()
                    sub_payload = sub.get_payload(decode=True)
                    if not isinstance(sub_payload, bytes):
                        continue
                    if sub_ct == "text/plain" and not fwd_text:
                        fwd_text = _to_text(sub_payload, sub.get_content_charset())
                    elif sub_ct == "text/html" and not fwd_html:
                        fwd_html = _to_text(sub_payload, sub.get_content_charset())
                fwd_body = fwd_text or _html_to_markdown(fwd_html)
            else:
                fwd_payload = forwarded_rfc822.get_payload(decode=True)
                if isinstance(fwd_payload, bytes):
                    raw_fwd = _to_text(fwd_payload, forwarded_rfc822.get_content_charset())
                    if forwarded_rfc822.get_content_type() == "text/html":
                        fwd_body = _html_to_markdown(raw_fwd)
                    else:
                        fwd_body = raw_fwd

            metadata["is_forwarded"] = True
            if fwd_from:
                metadata["forwarded_from"] = fwd_from
            if fwd_subject:
                metadata["forwarded_subject"] = fwd_subject
            if fwd_date:
                metadata["forwarded_date"] = fwd_date
            if fwd_body:
                metadata["forwarded_body"] = fwd_body
            content = content or fwd_body

        elif is_forwarded:
            parsed = parse_forwarded_body(text_body or content)
            if parsed:
                metadata["is_forwarded"] = True
                if parsed.get("forwarded_from"):
                    metadata["forwarded_from"] = parsed["forwarded_from"]
                if parsed.get("forwarded_subject"):
                    metadata["forwarded_subject"] = parsed["forwarded_subject"]
                if parsed.get("forwarded_date"):
                    metadata["forwarded_date"] = parsed["forwarded_date"]
                if parsed.get("forwarded_to"):
                    metadata["forwarded_to"] = parsed["forwarded_to"]
                if parsed["forwarded_body"]:
                    metadata["forwarded_body"] = parsed["forwarded_body"]
                content = parsed["annotation"] or parsed["forwarded_body"]
            else:
                metadata["is_forwarded"] = True

        # Written last: a message that fails is read again, so no file may exist before the rest of it has been read.
        media = _save_attachments(attachments)

        return self._build_inbound(
            sender_id=sender_email,
            content=content,
            chat_id=sender_email,
            is_group=False,
            mentioned=True,
            media=media,
            reply_to_id=in_reply_to or None,
            thread_id=thread_id,
            metadata=metadata,
            message_id=message_id or str(uid),
        )
