"""EmailChannel tests — lifecycle, send, health, collect_issues, inbound parsing."""

from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.email import EmailChannel
from app.channels.types import (
    ChannelStatus,
    IssueKind,
    MediaType,
    OutboundMessage,
)

from .channel_test_base import ChannelTestBase


class TestEmailChannelBase(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return EmailChannel(
            imap_host="",
            imap_user="",
            imap_password="",
            smtp_host="",
            smtp_user="",
            smtp_password="",
        )


def _make_channel(**overrides: str) -> EmailChannel:
    defaults = {
        "imap_host": "imap.example.com",
        "imap_user": "bot@example.com",
        "imap_password": "secret",
        "smtp_host": "smtp.example.com",
        "smtp_user": "bot@example.com",
        "smtp_password": "secret",
    }
    defaults.update(overrides)
    return EmailChannel(**defaults)  # type: ignore[arg-type]


class TestEmailLifecycle:
    @pytest.mark.asyncio
    async def test_start_success(self) -> None:
        ch = _make_channel()
        await ch.start()
        assert ch._status == ChannelStatus.RUNNING
        assert ch._poll_task is not None
        ch._poll_task.cancel()

    @pytest.mark.asyncio
    async def test_start_not_configured(self) -> None:
        ch = EmailChannel(
            imap_host="",
            imap_user="",
            imap_password="",
            smtp_host="",
            smtp_user="",
            smtp_password="",
        )
        await ch.start()
        assert ch._status != ChannelStatus.RUNNING
        assert ch._poll_task is None

    @pytest.mark.asyncio
    async def test_stop(self) -> None:
        ch = _make_channel()
        await ch.start()
        assert ch._poll_task is not None
        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED


class TestEmailHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_ok(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING

        mock_conn = MagicMock()
        mock_conn.login.return_value = ("OK", [])
        mock_conn.noop.return_value = ("OK", [])
        with patch("imaplib.IMAP4_SSL", return_value=mock_conn):
            result = await ch.health_check()
        assert result is True
        assert not ch.health.last_error

    @pytest.mark.asyncio
    async def test_health_check_failure(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING

        with patch("imaplib.IMAP4_SSL", side_effect=ConnectionRefusedError("refused")):
            result = await ch.health_check()
        assert result is False
        assert ch.health.last_error

    @pytest.mark.asyncio
    async def test_health_check_not_running(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.STOPPED
        result = await ch.health_check()
        assert result is False


class TestEmailSend:
    @pytest.mark.asyncio
    async def test_send_success(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(
            channel="email",
            user_id="u1",
            recipient_id="user@example.com",
            content="Hello!",
            metadata={"subject": "Test"},
        )

        mock_server = MagicMock()
        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
            result = await ch.send(msg)

        assert result is not None
        assert "@" in result

    @pytest.mark.asyncio
    async def test_send_ssl_port_465(self) -> None:
        ch = _make_channel()
        ch._smtp_port = 465
        msg = OutboundMessage(
            channel="email",
            user_id="u1",
            recipient_id="user@example.com",
            content="Hello!",
        )

        mock_server = MagicMock()
        with patch("smtplib.SMTP_SSL") as mock_smtp_ssl:
            mock_smtp_ssl.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp_ssl.return_value.__exit__ = MagicMock(return_value=False)
            result = await ch.send(msg)

        assert result is not None
        mock_smtp_ssl.assert_called_once_with("smtp.example.com", 465, timeout=30)

    @pytest.mark.asyncio
    async def test_send_empty_content(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(channel="email", user_id="u1", recipient_id="user@example.com", content="")
        result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_auth_error_not_retriable(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(
            channel="email",
            user_id="u1",
            recipient_id="user@example.com",
            content="Hello!",
        )

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_server.starttls.return_value = None
            mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"auth failed")
            mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(ChannelSendError) as exc_info:
                await ch.send(msg)
            assert exc_info.value.retriable is False

    @pytest.mark.asyncio
    async def test_send_network_error_retriable(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(
            channel="email",
            user_id="u1",
            recipient_id="user@example.com",
            content="Hello!",
        )

        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value.__enter__ = MagicMock(side_effect=OSError("Connection refused"))
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(ChannelSendError) as exc_info:
                await ch.send(msg)
            assert exc_info.value.retriable is True

    @pytest.mark.asyncio
    async def test_send_with_reply_to_id(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(
            channel="email",
            user_id="u1",
            recipient_id="user@example.com",
            content="Reply content",
            reply_to_id="<orig123@example.com>",
            metadata={"subject": "Re: Test"},
        )

        mock_server = MagicMock()
        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
            result = await ch.send(msg)

        assert result is not None
        sent_msg = mock_server.send_message.call_args[0][0]
        assert sent_msg["In-Reply-To"] == "<orig123@example.com>"
        assert sent_msg["References"] == "<orig123@example.com>"


class TestEmailCollectIssues:
    def test_not_configured(self) -> None:
        ch = EmailChannel(
            imap_host="",
            imap_user="",
            imap_password="",
            smtp_host="",
            smtp_user="",
            smtp_password="",
        )
        issues = ch.collect_issues()
        assert len(issues) >= 1
        assert any(i.kind == IssueKind.CONFIG for i in issues)

    def test_degraded_status(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.DEGRADED
        issues = ch.collect_issues()
        assert any(i.kind == IssueKind.RUNTIME for i in issues)

    def test_last_error(self) -> None:
        ch = _make_channel()
        ch.health.record_failure("SMTP timeout")
        issues = ch.collect_issues()
        assert any("SMTP timeout" in i.message for i in issues)

    def test_healthy_no_issues(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        issues = ch.collect_issues()
        assert len(issues) == 0


class TestEmailFetchNewEmails:
    def test_fetch_no_new_emails(self) -> None:
        ch = _make_channel()
        mock_conn = MagicMock()
        mock_conn.login.return_value = ("OK", [])
        mock_conn.select.return_value = ("OK", [b"1"])
        mock_conn.uid.return_value = ("OK", [b""])

        with patch("imaplib.IMAP4_SSL", return_value=mock_conn):
            results = ch._fetch_new_emails()
        assert results == []

    def test_fetch_with_new_email(self) -> None:
        import email.mime.text
        import email.utils

        msg = email.mime.text.MIMEText("New message", "plain")
        msg["From"] = "sender@example.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = "Test"
        msg["Message-ID"] = email.utils.make_msgid()

        ch = _make_channel()
        mock_conn = MagicMock()
        mock_conn.login.return_value = ("OK", [])
        mock_conn.select.return_value = ("OK", [b"1"])
        mock_conn.uid.side_effect = [
            ("OK", [b"1"]),
            ("OK", [(b"1 (RFC822 {100}", msg.as_bytes())]),
        ]

        with patch("imaplib.IMAP4_SSL", return_value=mock_conn):
            results = ch._fetch_new_emails()
        assert len(results) == 1
        assert results[0].sender_id == "sender@example.com"
        assert ch._last_uid == 1


class TestEmailParseInbound:
    def _raw_email(
        self,
        from_addr: str = "user@example.com",
        subject: str = "Test Subject",
        body: str = "Hello from email",
        in_reply_to: str = "",
    ) -> bytes:
        import email.mime.multipart
        import email.mime.text
        import email.utils

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = from_addr
        msg["To"] = "bot@example.com"
        msg["Subject"] = subject
        msg["Message-ID"] = email.utils.make_msgid()
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        msg.attach(email.mime.text.MIMEText(body, "plain"))
        return msg.as_bytes()

    def test_parse_simple_email(self) -> None:
        ch = _make_channel()
        raw = self._raw_email()
        result = ch._parse_email(raw, uid=1)

        assert result is not None
        assert result.sender_id == "user@example.com"
        assert "Hello from email" in result.content
        assert result.channel == "email"
        assert result.mentioned is True
        assert result.is_group is False

    def test_parse_email_from_self_filtered(self) -> None:
        ch = _make_channel()
        raw = self._raw_email(from_addr="bot@example.com")
        result = ch._parse_email(raw, uid=1)
        assert result is None

    def test_parse_email_with_reply(self) -> None:
        ch = _make_channel()
        raw = self._raw_email(in_reply_to="<original@example.com>")
        result = ch._parse_email(raw, uid=1)

        assert result is not None
        assert result.reply_to_id == "<original@example.com>"
        assert result.thread_id == "<original@example.com>"

    def test_parse_empty_email_filtered(self) -> None:
        ch = _make_channel()
        raw = self._raw_email(body="")
        result = ch._parse_email(raw, uid=1)
        assert result is None

    def test_parse_email_with_attachment(self) -> None:
        import email.mime.base
        import email.mime.multipart
        import email.mime.text
        import email.utils

        msg = email.mime.multipart.MIMEMultipart()
        msg["From"] = "user@example.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = "With attachment"
        msg["Message-ID"] = email.utils.make_msgid()
        msg.attach(email.mime.text.MIMEText("See attached", "plain"))

        attachment = email.mime.base.MIMEBase("application", "pdf")
        attachment.set_payload(b"fake pdf data")
        attachment.add_header("Content-Disposition", "attachment", filename="doc.pdf")
        msg.attach(attachment)

        ch = _make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert len(result.media) == 1
        assert result.media[0].media_type == MediaType.DOCUMENT
        assert result.media[0].filename == "doc.pdf"

    def test_parse_email_image_attachment(self) -> None:
        import email.mime.base
        import email.mime.multipart
        import email.mime.text
        import email.utils

        msg = email.mime.multipart.MIMEMultipart()
        msg["From"] = "user@example.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = "Image"
        msg["Message-ID"] = email.utils.make_msgid()
        msg.attach(email.mime.text.MIMEText("See image", "plain"))

        attachment = email.mime.base.MIMEBase("image", "png")
        attachment.set_payload(b"fake image")
        attachment.add_header("Content-Disposition", "attachment", filename="photo.png")
        msg.attach(attachment)

        ch = _make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert len(result.media) == 1
        assert result.media[0].media_type == MediaType.IMAGE

    def test_parse_noreply_sender_filtered(self) -> None:
        ch = _make_channel()
        raw = self._raw_email(from_addr="noreply@example.com")
        result = ch._parse_email(raw, uid=1)
        assert result is None

    def test_parse_mailer_daemon_filtered(self) -> None:
        ch = _make_channel()
        raw = self._raw_email(from_addr="mailer-daemon@example.com")
        result = ch._parse_email(raw, uid=1)
        assert result is None

    def test_parse_automated_header_filtered(self) -> None:
        import email.mime.multipart
        import email.mime.text
        import email.utils

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = "newsletter@shop.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = "Sale!"
        msg["Message-ID"] = email.utils.make_msgid()
        msg["Precedence"] = "bulk"
        msg.attach(email.mime.text.MIMEText("Buy now!", "plain"))

        ch = _make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)
        assert result is None

    def test_parse_list_unsubscribe_filtered(self) -> None:
        import email.mime.multipart
        import email.mime.text
        import email.utils

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = "updates@service.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = "Weekly digest"
        msg["Message-ID"] = email.utils.make_msgid()
        msg["List-Unsubscribe"] = "<mailto:unsub@service.com>"
        msg.attach(email.mime.text.MIMEText("Digest content", "plain"))

        ch = _make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)
        assert result is None

    def test_parse_rfc2047_subject_decoded(self) -> None:
        import email.mime.multipart
        import email.mime.text
        import email.utils
        from email.header import Header

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = "user@example.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = Header("你好世界", "utf-8").encode()
        msg["Message-ID"] = email.utils.make_msgid()
        msg.attach(email.mime.text.MIMEText("Content", "plain"))

        ch = _make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert result.metadata
        assert result.metadata["subject"] == "你好世界"

    def test_normal_sender_not_filtered(self) -> None:
        ch = _make_channel()
        raw = self._raw_email(from_addr="colleague@company.com")
        result = ch._parse_email(raw, uid=1)
        assert result is not None
        assert result.sender_id == "colleague@company.com"
