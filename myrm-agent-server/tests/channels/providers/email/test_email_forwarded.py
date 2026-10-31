"""EmailChannel forwarded-message parsing: the annotation and the original message of a forwarded email."""

from __future__ import annotations

from tests.channels.providers.email.email_channel_factory import make_channel


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

        ch = make_channel()
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

        Verifies text_body is used for separator parsing (HTML wraps
        separators in <div>, which breaks regex detection).
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

        ch = make_channel()
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

        ch = make_channel()
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

        ch = make_channel()
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

        ch = make_channel()
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

        ch = make_channel()
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
        body = "---------- Forwarded message ---------\nFrom: reports@company.com\nSubject: Report\n\nQ2 results are in..."
        msg.attach(email.mime.text.MIMEText(body, "plain"))

        ch = make_channel()
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

        ch = make_channel()
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

        ch = make_channel()
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

        ch = make_channel()
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
        body = "請查閱\n\n---------- 轉發郵件 ----------\nFrom: colleague@hk.example.com\nSubject: 會議紀要\n\n會議內容..."
        msg.attach(email.mime.text.MIMEText(body, "plain"))

        ch = make_channel()
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
            "<div>Review this</div>"
            '<div style="border-top:1px solid #ccc">'
            "<p><b>-----Original Message-----</b></p>"
            "<p>From: partner@corp.com<br>"
            "Subject: Contract Draft</p>"
            "<p>Please find the contract.</p></div>"
        )

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = "user@outlook.com"
        msg["To"] = "bot@example.com"
        msg["Subject"] = "FW: Contract Draft"
        msg["Message-ID"] = email.utils.make_msgid()
        msg.attach(email.mime.text.MIMEText(plain, "plain"))
        msg.attach(email.mime.text.MIMEText(html, "html"))

        ch = make_channel()
        result = ch._parse_email(msg.as_bytes(), uid=1)

        assert result is not None
        assert result.metadata["is_forwarded"] is True
        assert result.metadata["forwarded_from"] == "partner@corp.com"
        assert result.content == "Review this"
