"""Email channel — bidirectional messaging via IMAP (inbound) + SMTP (outbound).

Inbound: IMAP periodic poll → _parse_email → _emit_inbound
  - Supports text, HTML, attachments
  - Thread detection via In-Reply-To / References headers
Outbound: SMTP send (text/HTML)

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class)
- channels.types::OutboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- EmailChannel: Email bidirectional messaging Channel (IMAP + SMTP)

[POS]
Email channel implementation. Supports IMAP polling for inbox, SMTP sending,
attachment parsing, and thread tracking.
"""

from __future__ import annotations

import asyncio
import email as email_lib
import email.mime.multipart
import email.mime.text
import email.utils
import imaplib
import logging
import smtplib
from typing import Self

from app.channels.core.base import BaseChannel
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
            with smtplib.SMTP_SSL(self._smtp_host, self._smtp_port) as server:
                server.login(self._smtp_user, self._smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(self._smtp_host, self._smtp_port) as server:
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

        subject = msg.get("Subject", "")
        message_id = msg.get("Message-ID", "")
        in_reply_to = msg.get("In-Reply-To", "")
        references = msg.get("References", "")

        body = ""
        media_list: list[MediaAttachment] = []

        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                disp = str(part.get("Content-Disposition", ""))

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
                    media_list.append(MediaAttachment(media_type=mt, filename=filename, mime_type=ct))
                elif (ct == "text/plain" and not body) or (ct == "text/html" and not body):
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        body = payload.decode("utf-8", errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if isinstance(payload, bytes):
                body = payload.decode("utf-8", errors="replace")

        if not body.strip() and not media_list:
            return None

        thread_id = in_reply_to or (references.split()[-1] if references else None)

        metadata: dict[str, object] = {
            "subject": subject,
            "message_id": message_id,
            "uid": uid,
        }

        return self._build_inbound(
            sender_id=sender_email,
            content=body.strip(),
            chat_id=sender_email,
            is_group=False,
            mentioned=True,
            media=tuple(media_list),
            reply_to_id=in_reply_to or None,
            thread_id=thread_id,
            metadata=metadata,
            message_id=message_id or str(uid),
        )
