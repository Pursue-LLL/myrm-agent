"""Mail from the open internet is read as it arrives: raw UTF-8 headers (RFC 6532) and charset names Python has no codec for.

Each case is the raw bytes of a message handed to the real parser, because the failures come from what the standard
library returns for such bytes (a ``Header`` object instead of ``str``, a ``LookupError`` for the charset), not from
anything a hand-built message object would reproduce.
"""

from __future__ import annotations

import json

import pytest

from app.channels.types import InboundMessage
from tests.channels.providers.email.email_channel_factory import make_channel

_PLAIN = b"text/plain; charset=utf-8"
_BODY = "正文 Body".encode()


def _mail(headers: dict[str, bytes] | None = None, *, body: bytes = _BODY, content_type: bytes = _PLAIN) -> bytes:
    merged = {
        "From": b"sender@example.com",
        "To": b"bot@example.com",
        "Subject": b"Hello",
        "Message-ID": b"<m1@example.com>",
        **(headers or {}),
    }
    lines = [name.encode() + b": " + value for name, value in merged.items()]
    return b"\r\n".join([*lines, b"MIME-Version: 1.0", b"Content-Type: " + content_type, b"", body])


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
    return _mail({"Subject": b"Fwd: x"}, body=body, content_type=b"multipart/mixed; boundary=f")


def _parse(raw: bytes) -> InboundMessage:
    result = make_channel()._parse_email(raw, uid=1)
    assert result is not None
    return result


class TestRawUtf8Headers:
    def test_the_subject_is_read(self) -> None:
        assert _parse(_mail({"Subject": "发票".encode()})).metadata["subject"] == "发票"

    def test_a_sender_with_a_display_name_is_not_dropped(self) -> None:
        assert _parse(_mail({"From": "张三 <zhang@example.com>".encode()})).sender_id == "zhang@example.com"

    def test_the_thread_headers_are_plain_text(self) -> None:
        result = _parse(
            _mail(
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

        assert _parse(_mail({"References": references})).thread_id == "<原@example.com>"

    def test_an_automation_header_in_raw_utf8_still_marks_the_sender_automated(self) -> None:
        assert make_channel()._parse_email(_mail({"Auto-Submitted": "自动".encode()}), uid=1) is None

    def test_an_encoded_word_in_a_charset_python_lacks_is_read_as_text(self) -> None:
        assert _parse(_mail({"Subject": b"=?x-unknown?q?abc?="})).metadata["subject"] == "abc"

    def test_a_header_python_reads_without_help_is_unchanged(self) -> None:
        """Malformed but pure-ASCII thread headers pass through as the sender wrote them."""
        result = _parse(_mail({"Message-ID": b"<a b@c.com>", "In-Reply-To": b"<a@b.com>, <c@d.com>"}))

        assert result.metadata["message_id"] == "<a b@c.com>"
        assert result.reply_to_id == "<a@b.com>, <c@d.com>"


@pytest.mark.parametrize("charset", ["unknown-8bit", "x-unknown"])
class TestCharsetPythonHasNoCodecFor:
    """The sender names the charset; one Python cannot decode is read as UTF-8 instead of failing the message."""

    def test_a_plain_body(self, charset: str) -> None:
        assert "正文" in _parse(_mail(content_type=f"text/plain; charset={charset}".encode())).content

    def test_an_html_body(self, charset: str) -> None:
        body = "<p>正文</p>".encode()

        assert "正文" in _parse(_mail(body=body, content_type=f"text/html; charset={charset}".encode())).content

    def test_the_parts_of_an_alternative_body(self, charset: str) -> None:
        raw = _mail(
            body=_alternative(b"b", charset, "正文 plain", "<p>正文 html</p>"), content_type=b"multipart/alternative; boundary=b"
        )

        assert _parse(raw).content == "正文 plain"

    def test_a_forwarded_plain_message(self, charset: str) -> None:
        inner = _FORWARDED_HEADERS + f"Content-Type: text/plain; charset={charset}\r\n\r\n".encode() + "原文".encode()

        self._assert_forwarded(_parse(_forwarding(inner)))

    def test_a_forwarded_alternative_message(self, charset: str) -> None:
        inner = _FORWARDED_HEADERS + b"Content-Type: multipart/alternative; boundary=i\r\n\r\n"
        inner += _alternative(b"i", charset, "原文", "<p>原文 html</p>")

        self._assert_forwarded(_parse(_forwarding(inner)))

    @staticmethod
    def _assert_forwarded(result: InboundMessage) -> None:
        assert result.metadata["forwarded_body"] == "原文"
        assert result.metadata["forwarded_from"] == "orig@example.com"
        assert result.metadata["forwarded_subject"] == "发票"
        assert json.dumps(result.metadata, ensure_ascii=False)
