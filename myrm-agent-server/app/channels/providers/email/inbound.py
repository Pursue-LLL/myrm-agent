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
RFC 822 message into an InboundMessage.
"""

from __future__ import annotations

import email as email_lib
import email.header
import email.utils
import logging
import tempfile
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


def _is_automated_sender(address: str, msg: email_lib.message.Message) -> bool:
    """Detect automated/noreply senders to prevent reply loops."""
    addr = address.lower()
    if any(pat in addr for pat in _NOREPLY_PATTERNS):
        return True
    for hdr, reject_vals in _AUTOMATED_HEADERS.items():
        value = msg.get(hdr, "")
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


def _decode_header(raw: str) -> str:
    """Decode RFC 2047 encoded header (e.g. =?UTF-8?B?...?=) to plain text."""
    parts = email.header.decode_header(raw)
    decoded: list[str] = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _html_to_markdown(html: str) -> str:
    """Convert email HTML body to clean Markdown for LLM consumption."""
    if not html:
        return ""
    from myrm_agent_harness.toolkits.web_fetch.processing.html_to_markdown import HTML2Markdown

    converter = HTML2Markdown()
    converter.update_params(ignore_images=True)
    return converter.handle(html).strip()


class EmailInboundMixin(BaseChannel):
    """Email inbound message parsing for ``EmailChannel``.

    Requires the host class to provide the attributes below plus ``_build_inbound`` from ``BaseChannel``.
    """

    _from_address: str

    def _parse_email(self, raw: bytes, uid: int) -> InboundMessage | None:
        msg = email_lib.message_from_bytes(raw)

        from_header = msg.get("From", "")
        sender_email = email.utils.parseaddr(from_header)[1]
        if not sender_email or sender_email == self._from_address:
            return None
        if _is_automated_sender(sender_email, msg):
            logger.debug("Email: skipping automated sender %s", sender_email)
            return None

        subject = _decode_header(msg.get("Subject", ""))
        message_id = msg.get("Message-ID", "")
        in_reply_to = msg.get("In-Reply-To", "")
        references = msg.get("References", "")

        text_body = ""
        html_body = ""
        media_list: list[MediaAttachment] = []
        forwarded_rfc822: email_lib.message.Message | None = None

        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                disp = str(part.get("Content-Disposition", ""))

                if ct == "message/rfc822":
                    payload = part.get_payload()
                    if isinstance(payload, list) and payload:
                        forwarded_rfc822 = payload[0]
                    continue

                if "attachment" in disp:
                    filename = part.get_filename() or "attachment"
                    if ct.startswith("image/"):
                        mt = MediaType.IMAGE
                    elif ct.startswith("audio/"):
                        mt = MediaType.AUDIO
                    elif ct.startswith("video/"):
                        mt = MediaType.VIDEO
                    else:
                        mt = MediaType.DOCUMENT
                    file_data = part.get_payload(decode=True)
                    saved_path: str | None = None
                    if isinstance(file_data, bytes) and file_data:
                        suffix = Path(filename).suffix or ""
                        tmp = tempfile.NamedTemporaryFile(delete=False, prefix="email_att_", suffix=suffix)
                        tmp.write(file_data)
                        tmp.close()
                        saved_path = tmp.name
                    media_list.append(
                        MediaAttachment(
                            media_type=mt,
                            filename=filename,
                            mime_type=ct,
                            path=saved_path,
                        )
                    )
                elif ct == "text/html":
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    if isinstance(payload, bytes):
                        html_body = payload.decode(charset, errors="replace")
                elif ct == "text/plain" and not text_body:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    if isinstance(payload, bytes):
                        text_body = payload.decode(charset, errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            if isinstance(payload, bytes):
                decoded = payload.decode(charset, errors="replace")
                if msg.get_content_type() == "text/html":
                    html_body = decoded
                else:
                    text_body = decoded

        body = text_body or _html_to_markdown(html_body)

        if not body.strip() and not media_list:
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
            fwd_from = email.utils.parseaddr(forwarded_rfc822.get("From", ""))[1]
            fwd_subject = _decode_header(forwarded_rfc822.get("Subject", ""))
            fwd_date = forwarded_rfc822.get("Date", "")
            fwd_body = ""
            if forwarded_rfc822.is_multipart():
                fwd_text = ""
                fwd_html = ""
                for sub in forwarded_rfc822.walk():
                    sub_ct = sub.get_content_type()
                    sub_payload = sub.get_payload(decode=True)
                    if not isinstance(sub_payload, bytes):
                        continue
                    sub_charset = sub.get_content_charset() or "utf-8"
                    if sub_ct == "text/plain" and not fwd_text:
                        fwd_text = sub_payload.decode(sub_charset, errors="replace")
                    elif sub_ct == "text/html" and not fwd_html:
                        fwd_html = sub_payload.decode(sub_charset, errors="replace")
                fwd_body = fwd_text or _html_to_markdown(fwd_html)
            else:
                fwd_payload = forwarded_rfc822.get_payload(decode=True)
                if isinstance(fwd_payload, bytes):
                    fwd_charset = forwarded_rfc822.get_content_charset() or "utf-8"
                    raw_fwd = fwd_payload.decode(fwd_charset, errors="replace")
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

        return self._build_inbound(
            sender_id=sender_email,
            content=content,
            chat_id=sender_email,
            is_group=False,
            mentioned=True,
            media=tuple(media_list),
            reply_to_id=in_reply_to or None,
            thread_id=thread_id,
            metadata=metadata,
            message_id=message_id or str(uid),
        )
