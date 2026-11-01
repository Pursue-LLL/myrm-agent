"""The imap-smtp-email skill script treats as an attachment every part the sender attached, however the sender wrote it.

Whether a part is an attachment follows from its ``Content-Disposition`` and from whether it names a file. RFC 2183 makes
the disposition type case-insensitive, some mail clients attach a file as ``inline``, and older mailers give the name only
in ``Content-Type``. A part missed here is a file that ``read`` does not list and ``download`` reports as absent.

[INPUT]
- assets/prebuilt_skills/imap-smtp-email/scripts: mail_client.message and email_manager.py imported in process
- tests/assets/conftest.py: the script import path
- tests/support/email_skill_inprocess.py: the IMAP double and the in-process ``main``

[OUTPUT]
- Fails when a part attached with another case of ``attachment``, as ``inline`` with a file name, or with its name only in
  ``Content-Type`` is not an attachment of ``read`` and ``download``, when a text part that carries a file name or the word
  ``attachment`` in it, or a part that names nothing, becomes one, when the attachments of a message come in another order
  than they were attached, or when the body of a message holds an attachment

[POS]
In-process test of which parts count as attachments, next to ``test_imap_smtp_email_attachments.py``, which covers how they
are named and saved.
"""

from __future__ import annotations

import base64
import email
import importlib
import json
from pathlib import Path
from types import ModuleType

import pytest

from tests.support.email_skill_inprocess import conn_serving, run_main

_PDF = b"%PDF-1.4"
_PDF_TYPE = "Content-Type: application/pdf"
_NAMED_PDF_TYPE = 'Content-Type: application/pdf; name="a.pdf"'


@pytest.fixture
def message(skill_modules: None) -> ModuleType:
    return importlib.import_module("mail_client.message")


def _encoded(content: bytes) -> str:
    return base64.b64encode(content).decode()


def _part(*headers: str, content: bytes = _PDF) -> str:
    """One MIME part of a multipart message, with *headers* written as raw UTF-8."""
    lines = "".join(f"{line}\r\n" for line in headers)
    return f"--b\r\n{lines}Content-Transfer-Encoding: base64\r\n\r\n{_encoded(content)}\r\n"


def _mixed(*parts: str) -> bytes:
    head = 'From: a@x.test\r\nMessage-ID: <1@x.test>\r\nMIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary="b"\r\n\r\n'
    return (head + "".join(parts) + "--b--\r\n").encode()


def _leaf(*headers: str) -> bytes:
    """A message that is a single part."""
    lines = "".join(f"{line}\r\n" for line in headers)
    return f"From: a@x.test\r\nMessage-ID: <1@x.test>\r\n{lines}Content-Transfer-Encoding: base64\r\n\r\n{_encoded(_PDF)}\r\n".encode()


_TEXT_BODY = _part("Content-Type: text/plain", content=b"hi")

# The part headers of a file the sender attached, in each way a sender may write them.
_ATTACHED = [
    pytest.param((_PDF_TYPE, 'Content-Disposition: attachment; filename="a.pdf"'), id="lower-case"),
    pytest.param((_PDF_TYPE, 'Content-Disposition: Attachment; filename="a.pdf"'), id="capitalized"),
    pytest.param((_NAMED_PDF_TYPE, "Content-Disposition: ATTACHMENT; FILENAME=a.pdf"), id="upper-case"),
    pytest.param((_PDF_TYPE, "Content-Disposition: attachment"), id="without-a-name"),
    pytest.param((_NAMED_PDF_TYPE, "Content-Disposition: inline; filename=a.pdf"), id="inline-with-a-name"),
    pytest.param((_NAMED_PDF_TYPE,), id="name-only-in-the-type"),
    pytest.param(("Content-Type: text/plain", "Content-Disposition: attachment; filename=n.txt"), id="text-file"),
    pytest.param(
        ('Content-Type: application/pdf; name="发票.pdf"', "Content-Disposition: Attachment; filename=发票.pdf"), id="raw-utf-8"
    ),
]

# The part headers of what the sender did not attach, however much it looks like it.
_NOT_ATTACHED = [
    pytest.param((), id="plain-text"),
    pytest.param((_PDF_TYPE,), id="names-nothing"),
    pytest.param((_PDF_TYPE, "Content-Disposition: inline"), id="inline-without-a-name"),
    pytest.param((_PDF_TYPE, "Content-Disposition: "), id="empty-disposition"),
    pytest.param(('Content-Type: multipart/mixed; boundary="x"; name="a.zip"',), id="a-container-that-names-itself"),
    pytest.param(
        ("Content-Type: text/plain; name=n.txt", "Content-Disposition: inline; filename=n.txt"), id="inline-text-with-a-name"
    ),
    pytest.param(
        ("Content-Type: text/plain", 'Content-Disposition: inline; filename="attachment.txt"'), id="the-word-in-a-text-name"
    ),
]


@pytest.mark.parametrize("headers", _ATTACHED)
def test_a_part_is_an_attachment_however_the_sender_wrote_it(message: ModuleType, headers: tuple[str, ...]) -> None:
    stored = email.message_from_bytes(_leaf(*headers))

    assert list(message.attachment_parts(stored)) == [stored]


@pytest.mark.parametrize("headers", _NOT_ATTACHED)
def test_a_part_that_only_looks_like_an_attachment_is_not_one(message: ModuleType, headers: tuple[str, ...]) -> None:
    assert list(message.attachment_parts(email.message_from_bytes(_leaf(*headers)))) == []


def test_the_attachments_of_a_message_come_in_the_order_they_were_attached(message: ModuleType) -> None:
    stored = email.message_from_bytes(
        _mixed(
            _TEXT_BODY,
            _part('Content-Type: application/pdf; name="one.pdf"', "Content-Disposition: inline; filename=one.pdf"),
            _part(_PDF_TYPE),
            _part("Content-Type: application/zip", "Content-Disposition: ATTACHMENT; filename=two.zip"),
        )
    )

    assert [message.attachment_filename(part) for part in message.attachment_parts(stored)] == ["one.pdf", "two.zip"]


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(_mixed(_TEXT_BODY, _part(_PDF_TYPE, 'Content-Disposition: attachment; filename="a.pdf"')), id="lower-case"),
        pytest.param(_mixed(_TEXT_BODY, _part(_PDF_TYPE, 'Content-Disposition: Attachment; filename="a.pdf"')), id="capitalized"),
        pytest.param(
            _mixed(_TEXT_BODY, _part(_NAMED_PDF_TYPE, "Content-Disposition: ATTACHMENT; FILENAME=a.pdf")), id="upper-case"
        ),
        pytest.param(_mixed(_TEXT_BODY, _part(_NAMED_PDF_TYPE, "Content-Disposition: inline; filename=a.pdf")), id="inline"),
        pytest.param(_mixed(_TEXT_BODY, _part(_NAMED_PDF_TYPE)), id="name-only-in-the-type"),
        pytest.param(
            _leaf(_NAMED_PDF_TYPE, "Content-Disposition: attachment; filename=a.pdf"), id="a-message-that-is-one-attachment"
        ),
    ],
)
def test_read_lists_and_download_saves_an_attachment_however_it_was_written(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    raw: bytes,
) -> None:
    run_main(email_manager, monkeypatch, conn_serving(raw), "read", "1")
    listed = json.loads(capsys.readouterr().out)["attachments"]

    run_main(email_manager, monkeypatch, conn_serving(raw), "download", "1", "--output-dir", str(tmp_path))
    answer = json.loads(capsys.readouterr().out)

    assert [entry["filename"] for entry in listed] == ["a.pdf"]
    assert answer["status"] == "downloaded"
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == {"a.pdf": _PDF}


@pytest.mark.parametrize(
    ("raw", "body"),
    [
        pytest.param(
            _leaf(_PDF_TYPE, "Content-Disposition: attachment; filename=a.pdf"), "", id="a-message-that-is-one-attachment"
        ),
        pytest.param(
            _leaf("Content-Type: text/plain", "Content-Disposition: attachment; filename=n.txt"), "", id="a-text-file-alone"
        ),
        pytest.param(
            _mixed(_part("Content-Type: text/plain", "Content-Disposition: Attachment; filename=n.txt", content=b"notes")),
            "",
            id="a-text-file-whose-disposition-is-capitalized",
        ),
        pytest.param(
            _mixed(_part("Content-Type: text/plain", "Content-Disposition: inline; filename=n.txt", content=b"notes")),
            "notes",
            id="an-inline-text-part-with-a-name-is-the-body",
        ),
    ],
)
def test_the_body_of_a_message_never_holds_an_attachment(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    raw: bytes,
    body: str,
) -> None:
    run_main(email_manager, monkeypatch, conn_serving(raw), "read", "1")

    assert json.loads(capsys.readouterr().out)["body"] == body
