"""The imap-smtp-email skill script reads a message from the mailbox even when its charset or encoded words are unusable.

A message in a mailbox is untrusted input: the sender chooses its charset names and header encoding. A charset Python
has no codec for (``unknown-8bit``, ``x-unknown``), an encoded word whose base64 is malformed, or a header with raw
UTF-8 bytes (the parser returns a ``Header`` object for it, not a ``str``) would otherwise end the whole command in a stack
trace, so a single such message would blind ``check``, ``search``, ``read`` and ``reply``.

[INPUT]
- assets/prebuilt_skills/imap-smtp-email/scripts: mail_client.message imported in process
- tests/assets/conftest.py: the script import path

[OUTPUT]
- Fails when a header with a malformed encoded word, a header with raw UTF-8 bytes or a body in a charset Python does
  not know raises or is not summarized as text instead of being returned as written or read as UTF-8, when a header or
  body that does decode changes, when whitespace between encoded words is kept or dropped other than as RFC 2047 says,
  when a message id with raw UTF-8 bytes is not left out of the ids a threading header takes, or when an attachment is
  not named by its ``Content-Disposition`` or, failing that, its ``Content-Type``, or when an attached message is written out
  through the stock header folding, which on some interpreters cuts a header at a vertical tab or a file separator

[POS]
Message-decoding test of the prebuilt skill script, next to ``test_imap_smtp_email_commands.py``, which covers the
commands it sends.
"""

from __future__ import annotations

import email
import email.header
import email.message
import email.policy
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
        pytest.param("Re: =?utf-8?b?5Y+R56Wo?=", "Re: 发票", id="text-before-an-encoded-word"),
        pytest.param("=?utf-8?b?5Y+R56Wo?= <eve@example.test>", "发票 <eve@example.test>", id="encoded-name-before-an-address"),
        pytest.param("=?utf-8?b?5Y+R56Wo?=.pdf", "发票.pdf", id="text-glued-to-an-encoded-word"),
        pytest.param("=?utf-8?q?a?= =?iso-8859-1?q?b?=", "ab", id="space-between-two-encoded-words-is-dropped"),
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


@pytest.mark.parametrize("stored", ["<a@x.test>", "<a@x.test>\r\n <b@x.test>"], ids=["one-id", "folded-list"])
def test_ids_that_are_plain_ascii_are_returned_as_they_are(message: ModuleType, stored: str) -> None:
    value = email.message_from_bytes(f"References: {stored}\r\n\r\n".encode())["References"]

    assert message.ascii_msg_ids(value) == value


@pytest.mark.parametrize(
    ("stored", "ids"),
    [
        pytest.param(None, "", id="missing"),
        pytest.param("<发票@x.test>", "", id="the-only-id"),
        pytest.param("<a@x.test> <发票@x.test> <b@x.test>", "<a@x.test> <b@x.test>", id="one-of-three"),
    ],
)
def test_an_id_with_raw_utf_8_bytes_is_left_out(message: ModuleType, stored: str | None, ids: str) -> None:
    """A threading header holds ids, not encoded words, so an id the parser hands over as a ``Header`` is dropped."""
    value = None if stored is None else email.message_from_bytes(f"References: {stored}\r\n\r\n".encode())["References"]
    assert stored is None or isinstance(value, email.header.Header)

    assert message.ascii_msg_ids(value) == ids


@pytest.mark.parametrize(
    ("headers", "name"),
    [
        pytest.param([], "attachment", id="no-name"),
        pytest.param(['Content-Disposition: attachment; filename="=?utf-8?b??="'], "attachment", id="an-empty-encoded-word"),
        pytest.param(['Content-Disposition: attachment; filename="a.pdf"'], "a.pdf", id="plain"),
        pytest.param(["Content-Disposition: attachment; filename*=UTF-8''%E5%8F%91%E7%A5%A8.pdf"], "发票.pdf", id="rfc-2231"),
        pytest.param(['Content-Disposition: attachment; filename="=?utf-8?b?5Y+R56Wo?=.pdf"'], "发票.pdf", id="rfc-2047"),
        pytest.param(['Content-Disposition: attachment; filename="发票.pdf"'], "发票.pdf", id="raw-utf-8-disposition"),
        pytest.param(['Content-Type: application/pdf; name="发票.pdf"'], "发票.pdf", id="raw-utf-8-type-name"),
        pytest.param(
            ['Content-Type: application/pdf; name="x.pdf"', 'Content-Disposition: attachment; filename="发票.pdf"'],
            "发票.pdf",
            id="the-disposition-comes-first",
        ),
    ],
)
def test_an_attachment_is_named_by_its_disposition_or_its_type(message: ModuleType, headers: list[str], name: str) -> None:
    raw = "".join(f"{line}\r\n" for line in headers).encode() + b"\r\nbody"

    assert message.attachment_filename(email.message_from_bytes(raw)) == name


def test_an_attached_message_is_written_without_the_stock_header_folding(
    message: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On some interpreters the stock folding splits a header at a file separator or a vertical tab, so the writer must not use it."""

    def stock_folding(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("the stock header folding was used")

    monkeypatch.setattr(email.policy.EmailPolicy, "fold_binary", stock_folding)
    monkeypatch.setattr(email.policy.Compat32, "fold_binary", stock_folding)
    attached = "From: eve@x.test\r\nSubject: invoice\x1cX-Next: kept\r\n\r\nhello\r\n"
    raw = f'Content-Type: message/rfc822\r\nContent-Disposition: attachment; filename="fwd.eml"\r\n\r\n{attached}'.encode()

    part = next(message.attachment_parts(email.message_from_bytes(raw)))

    assert message.attachment_bytes(part) == attached.encode()
