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


class TestEmailForwardedParsing:
    """Tests for forwarded email detection and structured parsing."""

    def test_forwarded_subject_gmail(self) -> None:
        import email.mime.multipart
        import email.mime.text
        import email.utils

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = "user@gmail.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = "Fwd: Invoice #12345"
        msg["Message-ID"] = email.utils.make_msgid()
        body = (
            "帮我报销\n\n"
            "---------- Forwarded message ---------\n"
            "From: billing@vendor.com\n"
            "Date: Mon, Jul 14, 2025\n"
            "Subject: Invoice #12345\n"
            "To: user@gmail.com\n\n"
            "Dear Customer, Please find attached your invoice for $2,500."
        )
        msg.attach(email.mime.text.MIMEText(body, "plain"))

        ch = _make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert result.metadata["is_forwarded"] is True
        assert result.metadata["forwarded_from"] == "billing@vendor.com"
        assert result.metadata["forwarded_subject"] == "Invoice #12345"
        assert result.metadata["forwarded_date"] == "Mon, Jul 14, 2025"
        assert "Dear Customer" in str(result.metadata["forwarded_body"])
        assert result.content == "帮我报销"

    def test_forwarded_gmail_html_multipart(self) -> None:
        """Gmail forwards with multipart/alternative (plain + html).

        Bug scenario: html_body wraps separator in <div>, regex fails on HTML.
        Fix: parse_forwarded_body uses text_body when available.
        """
        import email.mime.multipart
        import email.mime.text
        import email.utils

        plain = (
            "帮我报销\n\n"
            "---------- Forwarded message ---------\n"
            "From: billing@vendor.com\n"
            "Date: Mon, Jul 14, 2025\n"
            "Subject: Invoice #12345\n"
            "To: user@gmail.com\n\n"
            "Dear Customer, Please find attached your invoice."
        )
        html = (
            '<div dir="ltr">帮我报销<br><br>'
            '<div class="gmail_quote"><div class="gmail_attr">'
            "---------- Forwarded message ---------<br>"
            "From: <strong>billing@vendor.com</strong><br>"
            "Date: Mon, Jul 14, 2025<br>"
            "Subject: Invoice #12345<br>"
            "To: user@gmail.com</div><br>"
            "Dear Customer, Please find attached your invoice."
            "</div></div>"
        )

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = "user@gmail.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = "Fwd: Invoice #12345"
        msg["Message-ID"] = email.utils.make_msgid()
        msg.attach(email.mime.text.MIMEText(plain, "plain"))
        msg.attach(email.mime.text.MIMEText(html, "html"))

        ch = _make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert result.metadata["is_forwarded"] is True
        assert result.metadata["forwarded_from"] == "billing@vendor.com"
        assert result.metadata["forwarded_subject"] == "Invoice #12345"
        assert result.content == "帮我报销"

    def test_forwarded_subject_outlook(self) -> None:
        import email.mime.multipart
        import email.mime.text
        import email.utils

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = "user@outlook.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = "FW: Meeting notes"
        msg["Message-ID"] = email.utils.make_msgid()
        body = (
            "See below\n\n"
            "-----Original Message-----\n"
            "From: boss@company.com\n"
            "Subject: Meeting notes\n\n"
            "Please review these notes."
        )
        msg.attach(email.mime.text.MIMEText(body, "plain"))

        ch = _make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert result.metadata["is_forwarded"] is True
        assert result.metadata["forwarded_from"] == "boss@company.com"
        assert result.metadata["forwarded_subject"] == "Meeting notes"
        assert result.content == "See below"

    def test_forwarded_subject_chinese(self) -> None:
        import email.mime.multipart
        import email.mime.text
        import email.utils

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = "user@qq.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = "转发: 客户需求"
        msg["Message-ID"] = email.utils.make_msgid()
        body = (
            "帮我整理一下\n\n"
            "---------- 转发邮件 ----------\n"
            "发件人: client@partner.com\n"
            "主题: 客户需求\n"
            "日期: 2025-07-14\n\n"
            "我们需要以下功能..."
        )
        msg.attach(email.mime.text.MIMEText(body, "plain"))

        ch = _make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert result.metadata["is_forwarded"] is True
        assert result.metadata["forwarded_from"] == "client@partner.com"
        assert result.metadata["forwarded_subject"] == "客户需求"
        assert result.content == "帮我整理一下"

    def test_forwarded_rfc822_mime_attachment(self) -> None:
        import email.mime.multipart
        import email.mime.text
        import email.utils
        from email.message import Message

        inner = Message()
        inner["From"] = "original@sender.com"
        inner["To"] = "user@gmail.com"
        inner["Subject"] = "Original Subject"
        inner["Date"] = "Mon, 14 Jul 2025 10:00:00 +0800"
        inner["Content-Type"] = "text/plain; charset=utf-8"
        inner.set_payload("Original message content")

        rfc822_part = Message()
        rfc822_part["Content-Type"] = "message/rfc822"
        rfc822_part.attach(inner)

        outer = email.mime.multipart.MIMEMultipart()
        outer["From"] = "user@gmail.com"
        outer["To"] = "bot@example.com"
        outer["Subject"] = "Fwd: Original Subject"
        outer["Message-ID"] = email.utils.make_msgid()
        outer.attach(email.mime.text.MIMEText("Check this out", "plain"))
        outer.attach(rfc822_part)

        ch = _make_channel()
        result = ch._parse_email(outer.as_bytes(), uid=1)

        assert result is not None
        assert result.metadata["is_forwarded"] is True
        assert result.metadata["forwarded_from"] == "original@sender.com"
        assert result.metadata["forwarded_subject"] == "Original Subject"
        assert "Original message content" in str(result.metadata["forwarded_body"])

    def test_forwarded_rfc822_multipart_inner(self) -> None:
        """RFC822 attachment with multipart inner message."""
        import email.mime.multipart
        import email.mime.text
        import email.utils
        from email.message import Message

        inner = email.mime.multipart.MIMEMultipart("alternative")
        inner["From"] = "deep@sender.com"
        inner["Subject"] = "Deep Subject"
        inner["Date"] = "Tue, 15 Jul 2025 10:00:00 +0800"
        inner.attach(email.mime.text.MIMEText("Plain inner", "plain"))
        inner.attach(email.mime.text.MIMEText("<b>HTML inner</b>", "html"))

        rfc822_part = Message()
        rfc822_part["Content-Type"] = "message/rfc822"
        rfc822_part.attach(inner)

        outer = email.mime.multipart.MIMEMultipart()
        outer["From"] = "user@gmail.com"
        outer["To"] = "bot@example.com"
        outer["Subject"] = "Fwd: Deep Subject"
        outer["Message-ID"] = email.utils.make_msgid()
        outer.attach(email.mime.text.MIMEText("See attached", "plain"))
        outer.attach(rfc822_part)

        ch = _make_channel()
        result = ch._parse_email(outer.as_bytes(), uid=1)

        assert result is not None
        assert result.metadata["is_forwarded"] is True
        assert result.metadata["forwarded_from"] == "deep@sender.com"
        assert result.metadata["forwarded_subject"] == "Deep Subject"
        assert "inner" in str(result.metadata.get("forwarded_body", "")).lower()

    def test_forwarded_no_annotation(self) -> None:
        """Forwarded email where user didn't add any annotation."""
        import email.mime.multipart
        import email.mime.text
        import email.utils

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = "user@gmail.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = "Fwd: Report"
        msg["Message-ID"] = email.utils.make_msgid()
        body = (
            "---------- Forwarded message ---------\n"
            "From: reports@company.com\n"
            "Subject: Report\n\n"
            "Q2 results are in..."
        )
        msg.attach(email.mime.text.MIMEText(body, "plain"))

        ch = _make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert result.metadata["is_forwarded"] is True
        assert "Q2 results" in result.content

    def test_non_forwarded_email_unaffected(self) -> None:
        """Normal (non-forwarded) email should have no forwarded metadata."""
        import email.mime.multipart
        import email.mime.text
        import email.utils

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = "user@example.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = "Hello"
        msg["Message-ID"] = email.utils.make_msgid()
        msg.attach(email.mime.text.MIMEText("Just a normal email", "plain"))

        ch = _make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert "is_forwarded" not in result.metadata
        assert result.content == "Just a normal email"

    def test_forwarded_subject_only_no_separator(self) -> None:
        """Email with Fwd: subject but no separator in body."""
        import email.mime.multipart
        import email.mime.text
        import email.utils

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = "user@example.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = "Fwd: Some topic"
        msg["Message-ID"] = email.utils.make_msgid()
        msg.attach(email.mime.text.MIMEText("Please handle this", "plain"))

        ch = _make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert result.metadata["is_forwarded"] is True
        assert result.content == "Please handle this"


    def test_forwarded_non_multipart_plain_text(self) -> None:
        """Non-multipart plain text forwarded email (simple clients)."""
        import email.message
        import email.utils

        msg = email.message.Message()
        msg["From"] = "user@example.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = "Fwd: Simple fwd"
        msg["Message-ID"] = email.utils.make_msgid()
        msg["Content-Type"] = "text/plain; charset=utf-8"
        body = (
            "Please check\n\n"
            "---------- Forwarded message ---------\n"
            "From: sender@external.com\n"
            "Subject: Original\n\n"
            "Original body content here"
        )
        msg.set_payload(body.encode("utf-8"))

        ch = _make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert result.metadata["is_forwarded"] is True
        assert result.metadata["forwarded_from"] == "sender@external.com"
        assert result.content == "Please check"

    def test_forwarded_traditional_chinese_subject(self) -> None:
        """Traditional Chinese forwarding prefix (轉發:)."""
        import email.mime.multipart
        import email.mime.text
        import email.utils

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = "user@hk.example.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = "轉發: 會議紀要"
        msg["Message-ID"] = email.utils.make_msgid()
        body = (
            "請查閱\n\n"
            "---------- 轉發郵件 ----------\n"
            "From: colleague@hk.example.com\n"
            "Subject: 會議紀要\n\n"
            "會議內容..."
        )
        msg.attach(email.mime.text.MIMEText(body, "plain"))

        ch = _make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert result.metadata["is_forwarded"] is True
        assert result.metadata["forwarded_from"] == "colleague@hk.example.com"
        assert result.content == "請查閱"

    def test_forwarded_outlook_html_multipart(self) -> None:
        """Outlook HTML multipart forwarding with -----Original Message-----."""
        import email.mime.multipart
        import email.mime.text
        import email.utils

        plain = (
            "Review this\n\n"
            "-----Original Message-----\n"
            "From: partner@corp.com\n"
            "Subject: Contract Draft\n\n"
            "Please find the contract."
        )
        html = (
            '<div>Review this</div>'
            '<div style="border-top:1px solid #ccc">'
            '<p><b>-----Original Message-----</b></p>'
            '<p>From: partner@corp.com<br>'
            'Subject: Contract Draft</p>'
            '<p>Please find the contract.</p></div>'
        )

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = "user@outlook.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = "FW: Contract Draft"
        msg["Message-ID"] = email.utils.make_msgid()
        msg.attach(email.mime.text.MIMEText(plain, "plain"))
        msg.attach(email.mime.text.MIMEText(html, "html"))

        ch = _make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert result.metadata["is_forwarded"] is True
        assert result.metadata["forwarded_from"] == "partner@corp.com"
        assert result.content == "Review this"


class TestEmailCharsetAndHtmlPriority:
    """Tests for charset detection and text/html priority fixes."""

    def test_html_preferred_over_plain(self) -> None:
        import email.mime.multipart
        import email.mime.text
        import email.utils

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = "user@example.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = "Multi-part"
        msg["Message-ID"] = email.utils.make_msgid()
        msg.attach(email.mime.text.MIMEText("Plain text version", "plain"))
        msg.attach(email.mime.text.MIMEText("<b>Rich</b> HTML version", "html"))

        ch = _make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert "<b>Rich</b>" in result.content

    def test_plain_used_when_no_html(self) -> None:
        import email.mime.multipart
        import email.mime.text
        import email.utils

        msg = email.mime.multipart.MIMEMultipart("mixed")
        msg["From"] = "user@example.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = "Plain only"
        msg["Message-ID"] = email.utils.make_msgid()
        msg.attach(email.mime.text.MIMEText("Only plain text", "plain"))

        ch = _make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert result.content == "Only plain text"

    def test_charset_gb2312_decoded(self) -> None:
        import email.mime.multipart
        import email.utils
        from email.mime.nonmultipart import MIMENonMultipart

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = "user@163.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = "Test"
        msg["Message-ID"] = email.utils.make_msgid()

        chinese_text = "你好世界"
        part = MIMENonMultipart("text", "plain", charset="gb2312")
        part.set_payload(chinese_text.encode("gb2312"))
        msg.attach(part)

        ch = _make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert "你好世界" in result.content
