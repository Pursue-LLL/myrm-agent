"""Email channel — bidirectional messaging via IMAP (inbound) + SMTP (outbound).

Inbound: IMAP periodic poll → _parse_email → _emit_inbound
  - Supports text, HTML, attachments
  - Thread detection via In-Reply-To / References headers
  - Forwarded message detection and structured parsing
Outbound: SMTP send (text/HTML)

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class)
- channels.types::OutboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- EmailChannel: Email bidirectional messaging Channel (IMAP + SMTP)

[POS]
Email channel implementation. Supports IMAP polling for inbox, SMTP sending,
attachment parsing, forwarded message parsing, and thread tracking.
"""

from __future__ import annotations

import asyncio
import email as email_lib
import email.header
import email.mime.multipart
import email.mime.text
import email.utils
import imaplib
import logging
import smtplib
import tempfile
from pathlib import Path
from typing import Self

from app.channels.core.base import BaseChannel
from app.channels.providers._email_forward import (
    FWD_SUBJECT_PREFIXES,
    parse_forwarded_body,
)
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.core.exceptions import ChannelSendError
from app.channels.reliability.reconnect import reconnect_loop
from app.channels.rendering.renderer import render
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    InboundMessage,
    IssueKind,
    IssueSeverity,
    MediaAttachment,
    MediaType,
    OutboundMessage,
    RenderStyle,
)

logger = logging.getLogger(__name__)

_MAX_TEXT_LENGTH = 100000
_POLL_INTERVAL = 30.0
_SMTP_TIMEOUT = 30

_NOREPLY_PATTERNS = (
    "noreply", "no-reply", "no_reply", "donotreply", "do-not-reply",
    "mailer-daemon", "postmaster", "bounce", "notifications@",
    "automated@", "auto-confirm", "auto-reply", "automailer",
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


def _send_imap_id(conn: imaplib.IMAP4_SSL) -> None:
    """Send RFC 2971 IMAP ID command. Required by 163/NetEase after LOGIN."""
    try:
        conn.xatom(
            "ID",
            '("name" "myrm-agent" "version" "1" '
            '"vendor" "myrm" "support-email" "noreply@myrm.sh")',
        )
    except Exception:
        pass


class EmailChannel(BaseChannel):
    """Email channel using IMAP inbound + SMTP outbound."""

    name = "email"
    credential_spec = credential_spec(
        "emailCredentials",
        imap_host=credential_field("imapHost", "EMAIL_IMAP_HOST"),
        imap_user=credential_field("imapUser", "EMAIL_IMAP_USER"),
        imap_password=credential_field("imapPassword", "EMAIL_IMAP_PASSWORD"),
        smtp_host=credential_field("smtpHost", "EMAIL_SMTP_HOST"),
        smtp_user=credential_field("smtpUser", "EMAIL_SMTP_USER"),
        smtp_password=credential_field("smtpPassword", "EMAIL_SMTP_PASSWORD"),
        imap_port=credential_field("imapPort", "EMAIL_IMAP_PORT", "993"),
        smtp_port=credential_field("smtpPort", "EMAIL_SMTP_PORT", "587"),
        from_address=credential_field("fromAddress", "EMAIL_FROM_ADDRESS"),
    )
    capabilities = ChannelCapabilities(
        text=True,
        markdown=True,
        media=True,
        file_upload=True,
        threads=True,
        max_text_length=_MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(
        format="html",
        max_text_length=_MAX_TEXT_LENGTH,
    )

    @classmethod
    def from_credentials(cls, creds: dict[str, str]) -> Self:
        return cls(
            imap_host=creds.get("imap_host", ""),
            imap_user=creds.get("imap_user", ""),
            imap_password=creds.get("imap_password", ""),
            smtp_host=creds.get("smtp_host", ""),
            smtp_user=creds.get("smtp_user", ""),
            smtp_password=creds.get("smtp_password", ""),
            imap_port=int(creds.get("imap_port", "993")),
            smtp_port=int(creds.get("smtp_port", "587")),
            from_address=creds.get("from_address", ""),
        )

    def __init__(
        self,
        imap_host: str,
        imap_user: str,
        imap_password: str,
        smtp_host: str,
        smtp_user: str,
        smtp_password: str,
        *,
        imap_port: int = 993,
        smtp_port: int = 587,
        from_address: str = "",
        poll_interval: float = _POLL_INTERVAL,
    ) -> None:
        super().__init__()
        self._imap_host = imap_host
        self._imap_port = imap_port
        self._imap_user = imap_user
        self._imap_password = imap_password
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._smtp_user = smtp_user
        self._smtp_password = smtp_password
        self._from_address = from_address or smtp_user
        self._poll_interval = poll_interval
        self._poll_task: asyncio.Task[None] | None = None
        self._last_uid: int = 0

    @property
    def _is_configured(self) -> bool:
        return bool(self._imap_host and self._smtp_host)

    async def start(self) -> None:
        if not self._is_configured:
            logger.debug("Email: not configured; channel idle")
            return
        await super().start()
        self._poll_task = asyncio.create_task(
            reconnect_loop(
                self._poll_once,
                lambda: self._status,
                channel_name="EmailChannel",
                max_backoff=120.0,
            )
        )
        logger.info("Email: started (%s)", self._imap_user)

    async def stop(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        await super().stop()
        logger.info("Email: stopped")

    async def health_check(self) -> bool:
        if self._status not in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            return False
        try:
            ok = await asyncio.to_thread(self._imap_ping)
            if ok:
                self.health.record_success()
            else:
                self.health.record_failure("IMAP NOOP failed")
            return ok
        except Exception as exc:
            self.health.record_failure(str(exc))
            return False

    async def send(self, msg: OutboundMessage) -> str | None:
        to_address = msg.recipient_id

        if not msg.content:
            return None

        chunks = render(msg, self.render_style)
        full_body = "\n".join(chunks)

        subject = "Reply"
        if msg.metadata:
            subject = str(msg.metadata.get("subject", subject))

        try:
            message_id = await asyncio.to_thread(
                self._smtp_send,
                to_address,
                subject,
                full_body,
                msg.reply_to_id,
            )
            self.health.record_success()
            return message_id
        except smtplib.SMTPAuthenticationError as exc:
            self.health.record_failure(f"SMTP auth: {exc}")
            raise ChannelSendError(
                "Email send failed: SMTP authentication error",
                channel=self.name,
                retriable=False,
            ) from exc
        except (smtplib.SMTPException, OSError) as exc:
            self.health.record_failure(str(exc))
            raise ChannelSendError(
                f"Email send failed: {exc}",
                channel=self.name,
                retriable=True,
            ) from exc

    def collect_issues(self) -> list[ChannelIssue]:
        issues: list[ChannelIssue] = []
        if not self._is_configured:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message="IMAP or SMTP host not configured",
                    fix="Set imap_host, smtp_host, and credentials in channel config",
                )
            )
        if self._status == ChannelStatus.DEGRADED:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.WARNING,
                    message="Email channel is in degraded state",
                )
            )
        if self.health.last_error:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.WARNING,
                    message=f"Last error: {self.health.last_error}",
                )
            )
        return issues

    def _imap_ping(self) -> bool:
        conn = imaplib.IMAP4_SSL(self._imap_host, self._imap_port)
        try:
            conn.login(self._imap_user, self._imap_password)
            _send_imap_id(conn)
            conn.noop()
            return True
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def _smtp_send(
        self,
        to_address: str,
        subject: str,
        body_html: str,
        in_reply_to: str | None = None,
    ) -> str:
        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = self._from_address
        msg["To"] = to_address
        msg["Subject"] = subject
        msg_id = email.utils.make_msgid()
        msg["Message-ID"] = msg_id

        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to

        msg.attach(email.mime.text.MIMEText(body_html, "html"))

        if self._smtp_port == 465:
            with smtplib.SMTP_SSL(
                self._smtp_host, self._smtp_port, timeout=_SMTP_TIMEOUT,
            ) as server:
                server.login(self._smtp_user, self._smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(
                self._smtp_host, self._smtp_port, timeout=_SMTP_TIMEOUT,
            ) as server:
                server.starttls()
                server.login(self._smtp_user, self._smtp_password)
                server.send_message(msg)

        return msg_id

    async def _poll_once(self) -> None:
        """Single poll cycle. reconnect_loop handles retry on failure."""
        while self._status == ChannelStatus.RUNNING:
            new_messages = await asyncio.to_thread(self._fetch_new_emails)
            for inbound in new_messages:
                await self._emit_inbound(inbound)
            await asyncio.sleep(self._poll_interval)

    def _fetch_new_emails(self) -> list[InboundMessage]:
        results: list[InboundMessage] = []
        conn = imaplib.IMAP4_SSL(self._imap_host, self._imap_port)
        try:
            conn.login(self._imap_user, self._imap_password)
            _send_imap_id(conn)
            conn.select("INBOX")

            if self._last_uid:
                criteria = f"(UID {self._last_uid + 1}:*)"
            else:
                criteria = "(UNSEEN)"

            _status, msg_nums = conn.uid("search", None, criteria)
            if not msg_nums or not msg_nums[0]:
                return results

            uids = msg_nums[0].split()
            for uid_bytes in uids[-20:]:
                uid = int(uid_bytes)
                if uid <= self._last_uid:
                    continue

                _status, data = conn.uid("fetch", str(uid), "(RFC822)")
                if not data or not data[0] or not isinstance(data[0], tuple):
                    continue

                raw = data[0][1]
                if isinstance(raw, bytes):
                    parsed = self._parse_email(raw, uid)
                    if parsed:
                        results.append(parsed)
                self._last_uid = max(self._last_uid, uid)

        finally:
            try:
                conn.logout()
            except Exception:
                pass

        return results

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
                        tmp = tempfile.NamedTemporaryFile(
                            delete=False, prefix="email_att_", suffix=suffix
                        )
                        tmp.write(file_data)
                        tmp.close()
                        saved_path = tmp.name
                    media_list.append(MediaAttachment(
                        media_type=mt, filename=filename, mime_type=ct, path=saved_path,
                    ))
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
                text_body = payload.decode(charset, errors="replace")

        body = html_body or text_body

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
            fwd_payload = forwarded_rfc822.get_payload(decode=True)
            fwd_body = ""
            if isinstance(fwd_payload, bytes):
                fwd_charset = forwarded_rfc822.get_content_charset() or "utf-8"
                fwd_body = fwd_payload.decode(fwd_charset, errors="replace")
            elif forwarded_rfc822.is_multipart():
                for sub in forwarded_rfc822.walk():
                    if sub.get_content_type() in ("text/plain", "text/html"):
                        sub_payload = sub.get_payload(decode=True)
                        if isinstance(sub_payload, bytes):
                            sub_charset = sub.get_content_charset() or "utf-8"
                            fwd_body = sub_payload.decode(sub_charset, errors="replace")
                            break

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
