"""EmailChannel inbound parsing — RFC 822 to ``InboundMessage``: bodies, charsets, attachments and thread headers."""

from __future__ import annotations

from app.channels.types import MediaType
from tests.channels.providers.email.email_channel_factory import make_channel


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
        ch = make_channel()
        raw = self._raw_email()
        result = ch._parse_email(raw, uid=1)

        assert result is not None
        assert result.sender_id == "user@example.com"
        assert "Hello from email" in result.content
        assert result.channel == "email"
        assert result.mentioned is True
        assert result.is_group is False

    def test_parse_email_from_self_filtered(self) -> None:
        ch = make_channel()
        raw = self._raw_email(from_addr="bot@example.com")
        result = ch._parse_email(raw, uid=1)
        assert result is None

    def test_parse_email_with_reply(self) -> None:
        ch = make_channel()
        raw = self._raw_email(in_reply_to="<original@example.com>")
        result = ch._parse_email(raw, uid=1)

        assert result is not None
        assert result.reply_to_id == "<original@example.com>"
        assert result.thread_id == "<original@example.com>"

    def test_parse_empty_email_filtered(self) -> None:
        ch = make_channel()
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

        ch = make_channel()
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

        ch = make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert len(result.media) == 1
        assert result.media[0].media_type == MediaType.IMAGE

    def test_parse_noreply_sender_filtered(self) -> None:
        ch = make_channel()
        raw = self._raw_email(from_addr="noreply@example.com")
        result = ch._parse_email(raw, uid=1)
        assert result is None

    def test_parse_mailer_daemon_filtered(self) -> None:
        ch = make_channel()
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

        ch = make_channel()
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

        ch = make_channel()
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

        ch = make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert result.metadata
        assert result.metadata["subject"] == "你好世界"

    def test_normal_sender_not_filtered(self) -> None:
        ch = make_channel()
        raw = self._raw_email(from_addr="colleague@company.com")
        result = ch._parse_email(raw, uid=1)
        assert result is not None
        assert result.sender_id == "colleague@company.com"


class TestEmailCharsetAndHtmlPriority:
    """Tests for charset detection and text/html priority fixes."""

    def test_plain_preferred_over_html(self) -> None:
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

        ch = make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert result.content == "Plain text version"

    def test_html_fallback_cleaned_when_no_plain(self) -> None:
        import email.mime.multipart
        import email.mime.text
        import email.utils

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = "user@example.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = "HTML only"
        msg["Message-ID"] = email.utils.make_msgid()
        msg.attach(email.mime.text.MIMEText("<h1>Hello</h1><p>World</p>", "html"))

        ch = make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert "<h1>" not in result.content
        assert "Hello" in result.content
        assert "World" in result.content

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

        ch = make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert result.content == "Only plain text"

    def test_non_multipart_html_cleaned(self) -> None:
        """Non-multipart email with Content-Type: text/html gets HTML cleaned."""
        raw = (
            b"From: billing@company.com\r\n"
            b"To: bot@example.com\r\n"
            b"Subject: Invoice\r\n"
            b"Message-ID: <inv@company.com>\r\n"
            b"Content-Type: text/html; charset=utf-8\r\n"
            b"\r\n"
            b"<html><head><style>.inv{border:1px solid}</style></head>"
            b"<body><h2>Invoice #123</h2><p>Total: $49.99</p></body></html>"
        )
        ch = make_channel()
        result = ch._parse_email(raw, uid=1)

        assert result is not None
        assert "<html>" not in result.content
        assert "<style>" not in result.content
        assert "Invoice #123" in result.content
        assert "$49.99" in result.content

    def test_non_multipart_plain_unchanged(self) -> None:
        """Non-multipart email with Content-Type: text/plain is unchanged."""
        raw = (
            b"From: user@example.com\r\n"
            b"To: bot@example.com\r\n"
            b"Subject: Hello\r\n"
            b"Message-ID: <hello@example.com>\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"Just a plain text email"
        )
        ch = make_channel()
        result = ch._parse_email(raw, uid=1)

        assert result is not None
        assert result.content == "Just a plain text email"

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

        ch = make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert "你好世界" in result.content
