"""Mail from the open internet is read as it arrives: raw UTF-8 headers (RFC 6532), charset names Python has no codec for
and encoded words that are spaced or cut off oddly.

Each case is the raw bytes of a message handed to the real parser, because the failures come from what the standard
library returns for such bytes (a ``Header`` object instead of ``str``, a ``LookupError`` for the charset, a
``HeaderParseError`` for a cut-off encoded word), not from anything a hand-built message object would reproduce.
"""

from __future__ import annotations

import json

import pytest

from app.channels.types import InboundMessage
from tests.channels.providers.email.email_channel_factory import make_channel, parse_inbound, raw_message


def _alternative(boundary: bytes, charset: str, plain: str, html: str) -> bytes:
    """The body of a multipart message whose plain and html parts both declare *charset*."""
    dash = b"--" + boundary + b"\r\n"
    return (
        dash
        + f"Content-Type: text/plain; charset={charset}\r\n\r\n".encode()
        + plain.encode()
        + b"\r\n"
        + dash
        + f"Content-Type: text/html; charset={charset}\r\n\r\n".encode()
        + html.encode()
        + b"\r\n--"
        + boundary
        + b"--\r\n"
    )


_FORWARDED_HEADERS = "From: 原始 <orig@example.com>\r\nSubject: 发票\r\nDate: 周一, 14 Jul 2025 10:00:00 +0800\r\n".encode()


def _forwarding(inner: bytes) -> bytes:
    """A message that forwards *inner* as a ``message/rfc822`` part."""
    body = (
        b"--f\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nSee below\r\n"
        b"--f\r\nContent-Type: message/rfc822\r\n\r\n" + inner + b"\r\n--f--\r\n"
    )
    return raw_message({"Subject": b"Fwd: x"}, body=body, content_type=b"multipart/mixed; boundary=f")


class TestRawUtf8Headers:
    def test_the_subject_is_read(self) -> None:
        assert parse_inbound(raw_message({"Subject": "发票".encode()})).metadata["subject"] == "发票"

    def test_a_sender_with_a_display_name_is_not_dropped(self) -> None:
        assert parse_inbound(raw_message({"From": "张三 <zhang@example.com>".encode()})).sender_id == "zhang@example.com"

    def test_the_thread_headers_are_plain_text(self) -> None:
        result = parse_inbound(
            raw_message(
                {
                    "Message-ID": "<发票@example.com>".encode(),
                    "In-Reply-To": "<原@example.com>".encode(),
                    "References": "<根@example.com> <原@example.com>".encode(),
                }
            )
        )

        assert result.metadata["message_id"] == "<发票@example.com>"
        assert result.reply_to_id == "<原@example.com>"
        assert result.thread_id == "<原@example.com>"
        assert {type(value) for value in (result.metadata["message_id"], result.reply_to_id, result.thread_id)} == {str}
        assert json.dumps(result.metadata, ensure_ascii=False)

    def test_the_last_reference_starts_the_thread_when_there_is_no_in_reply_to(self) -> None:
        references = "<根@example.com> <原@example.com>".encode()

        assert parse_inbound(raw_message({"References": references})).thread_id == "<原@example.com>"

    def test_an_automation_header_in_raw_utf8_still_marks_the_sender_automated(self) -> None:
        assert make_channel()._parse_email(raw_message({"Auto-Submitted": "自动".encode()}), uid=1) is None

    def test_an_encoded_word_in_a_charset_python_lacks_is_read_as_text(self) -> None:
        assert parse_inbound(raw_message({"Subject": b"=?x-unknown?q?abc?="})).metadata["subject"] == "abc"

    def test_a_header_python_reads_without_help_is_unchanged(self) -> None:
        """Malformed but pure-ASCII thread headers pass through as the sender wrote them."""
        result = parse_inbound(raw_message({"Message-ID": b"<a b@c.com>", "In-Reply-To": b"<a@b.com>, <c@d.com>"}))

        assert result.metadata["message_id"] == "<a b@c.com>"
        assert result.reply_to_id == "<a@b.com>, <c@d.com>"


class TestEncodedWordSubject:
    """The subject is the text a reply is addressed with, so it must read as the sender meant it."""

    def test_the_spaces_beside_an_encoded_word_are_the_senders(self) -> None:
        raw = raw_message({"Subject": b"Your =?utf-8?q?caf=C3=A9?= order"})

        assert parse_inbound(raw).metadata["subject"] == "Your café order"

    def test_nothing_is_added_between_adjacent_encoded_words(self) -> None:
        """White space that only separates two encoded words is not part of the text (RFC 2047 section 6.2)."""
        raw = raw_message({"Subject": b"=?utf-8?q?caf=C3=A9?= =?iso-8859-1?q?cr=E8me?="})

        assert parse_inbound(raw).metadata["subject"] == "cafécrème"

    def test_a_cut_off_encoded_word_stays_as_written_and_the_mail_is_delivered(self) -> None:
        """A base64 word with a stray last character cannot be decoded; the message is still read."""
        raw = raw_message({"Subject": b"Re: =?utf-8?b?5Y+R56Wo5?="})

        assert parse_inbound(raw).metadata["subject"] == "Re: =?utf-8?b?5Y+R56Wo5?="


@pytest.mark.parametrize("charset", ["unknown-8bit", "x-unknown"])
class TestCharsetPythonHasNoCodecFor:
    """The sender names the charset; one Python cannot decode is read as UTF-8 instead of failing the message."""

    def test_a_plain_body(self, charset: str) -> None:
        assert "正文" in parse_inbound(raw_message(content_type=f"text/plain; charset={charset}".encode())).content

    def test_an_html_body(self, charset: str) -> None:
        body = "<p>正文</p>".encode()

        assert "正文" in parse_inbound(raw_message(body=body, content_type=f"text/html; charset={charset}".encode())).content

    def test_the_parts_of_an_alternative_body(self, charset: str) -> None:
        raw = raw_message(
            body=_alternative(b"b", charset, "正文 plain", "<p>正文 html</p>"), content_type=b"multipart/alternative; boundary=b"
        )

        assert parse_inbound(raw).content == "正文 plain"

    def test_a_forwarded_plain_message(self, charset: str) -> None:
        inner = _FORWARDED_HEADERS + f"Content-Type: text/plain; charset={charset}\r\n\r\n".encode() + "原文".encode()

        self._assert_forwarded(parse_inbound(_forwarding(inner)))

    def test_a_forwarded_alternative_message(self, charset: str) -> None:
        inner = _FORWARDED_HEADERS + b"Content-Type: multipart/alternative; boundary=i\r\n\r\n"
        inner += _alternative(b"i", charset, "原文", "<p>原文 html</p>")

        self._assert_forwarded(parse_inbound(_forwarding(inner)))

    @staticmethod
    def _assert_forwarded(result: InboundMessage) -> None:
        assert result.metadata["forwarded_body"] == "原文"
        assert result.metadata["forwarded_from"] == "orig@example.com"
        assert result.metadata["forwarded_subject"] == "发票"
        assert json.dumps(result.metadata, ensure_ascii=False)
