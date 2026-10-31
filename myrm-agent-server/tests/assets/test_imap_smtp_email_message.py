"""The imap-smtp-email skill script reads a message from the mailbox even when its charset or encoded words are unusable.

A message in a mailbox is untrusted input: the sender chooses its charset names and header encoding. A charset Python
has no codec for (``unknown-8bit``, ``x-unknown``), an encoded word whose base64 is malformed, or a header with raw
UTF-8 bytes (the parser returns a ``Header`` object for it, not a ``str``) used to end the whole command in a stack
trace, so a single such message blinded ``check``, ``search``, ``read`` and ``reply``.

[INPUT]
- assets/prebuilt_skills/imap-smtp-email/scripts: mail_client.message imported in process
- tests/assets/conftest.py: the script import path

[OUTPUT]
- Fails when a header with a malformed encoded word, a header with raw UTF-8 bytes or a body in a charset Python does
  not know raises or is not summarized as text instead of being returned as written or read as UTF-8, or when a header
  or body that does decode changes

[POS]
Message-decoding test of the prebuilt skill script, next to ``test_imap_smtp_email_commands.py``, which covers the
commands it sends.
"""

from __future__ import annotations

import email
import email.message
import importlib
import json
from types import ModuleType

import pytest


@pytest.fixture
def message(skill_modules: None) -> ModuleType:
    return importlib.import_module("mail_client.message")


@pytest.mark.parametrize(
    ("raw", "text"),
    [
        pytest.param(None, "", id="missing"),
        pytest.param("plain", "plain", id="plain"),
        pytest.param("=?utf-8?b?5Y+R56Wo?=", "发票", id="base64-word"),
        pytest.param("=?utf-8?b?A?=", "=?utf-8?b?A?=", id="malformed-base64-is-returned-as-written"),
        pytest.param("=?x-unknown?b?QQ==?=", "A", id="unknown-charset-is-read-as-utf-8"),
    ],
)
def test_a_header_is_decoded_and_an_unusable_one_does_not_raise(message: ModuleType, raw: str | None, text: str) -> None:
    assert message.decode_header(raw) == text


def _stored(content_type: str, body: bytes) -> email.message.Message:
    head = f"Content-Type: {content_type}\r\nContent-Transfer-Encoding: 8bit\r\n\r\n".encode()
    return email.message_from_bytes(head + body)


@pytest.mark.parametrize(
    ("charset", "body", "text"),
    [
        pytest.param("utf-8", "发票".encode(), "发票", id="utf-8"),
        pytest.param("iso-8859-1", b"caf\xe9", "café", id="declared-charset-is-honored"),
        pytest.param("unknown-8bit", b"hello", "hello", id="unknown-8bit"),
        pytest.param("x-unknown", b"hello", "hello", id="unknown-name"),
        pytest.param("utf\x00x", b"hello", "hello", id="nul-in-the-name"),
    ],
)
def test_a_single_part_body_is_read_in_its_charset_or_as_utf_8(message: ModuleType, charset: str, body: bytes, text: str) -> None:
    assert message.extract_body(_stored(f'text/plain; charset="{charset}"', body)) == text


def test_every_part_of_a_multipart_body_is_decoded_even_when_a_charset_is_unknown(message: ModuleType) -> None:
    raw = (
        b'Content-Type: multipart/alternative; boundary="b"\r\n\r\n'
        b'--b\r\nContent-Type: text/plain; charset="x-unknown"\r\nContent-Transfer-Encoding: 8bit\r\n\r\nplain\r\n'
        b'--b\r\nContent-Type: text/html; charset="unknown-8bit"\r\nContent-Transfer-Encoding: 8bit\r\n\r\n<p>html</p>\r\n'
        b"--b--\r\n"
    )

    assert message.extract_body(email.message_from_bytes(raw)).strip() == "plain"


def test_a_summary_of_a_message_with_a_malformed_subject_still_lists_it(message: ModuleType) -> None:
    raw = b"From: eve@example.test\r\nSubject: =?utf-8?b?A?=\r\nDate: Mon, 02 Nov 2026 10:00:00 +0000\r\n\r\nbody\r\n"

    summary = message.message_summary(email.message_from_bytes(raw), 7)

    assert summary["uid"] == 7
    assert summary["from"] == "eve@example.test"
    assert summary["subject"] == "=?utf-8?b?A?="


@pytest.mark.parametrize(
    ("header", "value", "field", "text"),
    [
        pytest.param("From", "发票 <eve@example.test>", "from", "发票 <eve@example.test>", id="from"),
        pytest.param("To", "发票 <bob@example.test>", "to", "发票 <bob@example.test>", id="to"),
        pytest.param("Subject", "发票", "subject", "发票", id="subject"),
        pytest.param("Date", "周一, 02 11月 2026 10:00:00 +0000", "date", None, id="date"),
        pytest.param("Message-ID", "<发票@example.test>", "message_id", None, id="message-id"),
    ],
)
def test_a_header_with_raw_utf_8_bytes_is_summarized_as_text(
    message: ModuleType, header: str, value: str, field: str, text: str | None
) -> None:
    """Raw UTF-8 in a header makes the parser return a ``Header`` object, which ``check`` and ``read`` cannot print as JSON."""
    fields = {
        "From": "eve@example.test",
        "To": "bob@example.test",
        "Subject": "invoice",
        "Date": "Mon, 02 Nov 2026 10:00:00 +0000",
        "Message-ID": "<1@example.test>",
        header: value,
    }
    raw = "".join(f"{name}: {content}\r\n" for name, content in fields.items()).encode() + b"\r\nbody\r\n"

    summary = message.message_summary(email.message_from_bytes(raw), 7)

    assert isinstance(summary[field], str)
    written = json.loads(json.dumps(summary, ensure_ascii=False))
    if text is not None:
        assert written[field] == text
