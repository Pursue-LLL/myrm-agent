"""The imap-smtp-email skill script treats as an attachment every part the sender attached, however the sender wrote it.

Whether a part is an attachment follows from its ``Content-Disposition`` and from whether it names a file. RFC 2183 makes
the disposition type case-insensitive, a sender may write a file as an ``inline`` part that has a name, and the name may be
given only in ``Content-Type``. A part missed here is a file that ``read`` does not list and ``download`` reports as absent;
an image the HTML body embeds is part of the body, not a file the sender attached. ``download`` saves an attached message
as the message it was.

[INPUT]
- assets/prebuilt_skills/imap-smtp-email/scripts: mail_client.message and email_manager.py imported in process
- tests/assets/conftest.py: the script import path
- tests/support/email_skill_inprocess.py: the IMAP double and the in-process ``main``

[OUTPUT]
- Fails when a part attached with another case of ``attachment``, as ``inline`` with a file name, or with its name only in
  ``Content-Type`` is not an attachment of ``read`` and ``download``, when a text part that carries a file name or the word
  ``attachment`` in it, or a part that names nothing, becomes one, when the attachments of a message come in another order
  than they were attached, when the body of a message holds an attachment, when an image that the HTML body points at with
  a ``cid:`` URL is listed or saved although nothing else makes it an attachment, or when one that is not pointed at, or
  that is attached by its disposition, is not; when an attached message is not saved as it was sent, raw UTF-8, long lines
  and control characters in a header included, or the attachments inside it are no longer listed and saved on their own

[POS]
In-process test of which parts count as attachments and what is saved from an attached message, next to
``test_imap_smtp_email_attachments.py``, which covers how attachments are named and saved.
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


def _part(*headers: str, content: bytes = _PDF, boundary: str = "b") -> str:
    """One MIME part of a multipart message, with *headers* written as raw UTF-8."""
    lines = "".join(f"{line}\r\n" for line in headers)
    return f"--{boundary}\r\n{lines}Content-Transfer-Encoding: base64\r\n\r\n{_encoded(content)}\r\n"


def _related(body: str, *images: str, body_type: str = "text/html") -> str:
    """A ``multipart/related`` part of a ``multipart/mixed`` message: a *body* and the *images* made with boundary ``r``."""
    text = _part(f"Content-Type: {body_type}; charset=utf-8", content=body.encode(), boundary="r")
    return f'--b\r\nContent-Type: multipart/related; boundary="r"\r\n\r\n{text}{"".join(images)}--r--\r\n'


def _attached_message(message: str, *headers: str) -> str:
    """A ``message/rfc822`` part of a ``multipart/mixed`` message; *message* is written into it as it is."""
    lines = "".join(f"{line}\r\n" for line in headers)
    return f"--b\r\nContent-Type: message/rfc822\r\n{lines}\r\n{message}\r\n"


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


_LOGO = ('Content-Type: image/png; name="logo.png"', 'Content-Disposition: inline; filename="logo.png"')


@pytest.mark.parametrize(
    ("html", "image", "kept"),
    [
        pytest.param('<img src="cid:i1">', (*_LOGO, "Content-ID: <i1>"), [], id="pointed-at"),
        pytest.param('<img src="CID:i1">', (*_LOGO, "Content-ID: <i1>"), [], id="scheme-in-upper-case"),
        pytest.param("<img src='cid:i1' alt=''>", (*_LOGO, "Content-ID: <i1>"), [], id="single-quoted"),
        pytest.param('<img src="cid:a%40b.test">', (*_LOGO, "Content-ID: <a@b.test>"), [], id="id-written-percent-encoded"),
        pytest.param('<img src="cid:a%25b@c.test">', (*_LOGO, "Content-ID: <a%25b@c.test>"), [], id="percent-sign-written-as-is"),
        pytest.param('<img src="cid:a%25b@c.test">', (*_LOGO, "Content-ID: <a%b@c.test>"), [], id="percent-sign-decoded"),
        pytest.param('<img src="cid:发票">', (*_LOGO, "Content-ID: <发票>"), [], id="id-in-raw-utf-8"),
        pytest.param("<p>no picture</p>", (*_LOGO, "Content-ID: <i1>"), ["logo.png"], id="never-pointed-at"),
        pytest.param('<img src="cid:other">', (*_LOGO, "Content-ID: <i1>"), ["logo.png"], id="another-id-pointed-at"),
        pytest.param('<img src="cid:i1x">', (*_LOGO, "Content-ID: <i1>"), ["logo.png"], id="longer-id-pointed-at"),
        pytest.param('<img src="cid:I1">', (*_LOGO, "Content-ID: <i1>"), ["logo.png"], id="id-in-another-case"),
        pytest.param('<img src="cid:i1">', _LOGO, ["logo.png"], id="no-content-id"),
        pytest.param(
            '<img src="cid:i1">',
            (
                'Content-Type: image/png; name="logo.png"',
                'Content-Disposition: attachment; filename="logo.png"',
                "Content-ID: <i1>",
            ),
            ["logo.png"],
            id="attached-by-its-disposition",
        ),
    ],
)
def test_an_image_the_html_body_points_at_is_not_a_file_the_sender_attached(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    html: str,
    image: tuple[str, ...],
    kept: list[str],
) -> None:
    """An image of the body is written as an inline part with a name and a Content-ID, which the HTML points at (RFC 2392)."""
    report = _part('Content-Type: application/pdf; name="report.pdf"', 'Content-Disposition: attachment; filename="report.pdf"')
    raw = _mixed(_related(html, _part(*image, boundary="r")), report)
    expected = [*kept, "report.pdf"]

    run_main(email_manager, monkeypatch, conn_serving(raw), "read", "1")
    read = json.loads(capsys.readouterr().out)
    run_main(email_manager, monkeypatch, conn_serving(raw), "download", "1", "--output-dir", str(tmp_path))
    capsys.readouterr()

    assert [entry["filename"] for entry in read["attachments"]] == expected
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(expected)
    assert read["body"] == html


def test_an_image_pointed_at_only_from_plain_text_is_still_an_attachment(message: ModuleType) -> None:
    stored = email.message_from_bytes(
        _mixed(_related("see cid:i1", _part(*_LOGO, "Content-ID: <i1>", boundary="r"), body_type="text/plain"))
    )

    assert [message.attachment_filename(part) for part in message.attachment_parts(stored)] == ["logo.png"]


_FORWARDED = "From: eve@x.test\r\nSubject: invoice\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nhello\r\n"
_FORWARDED_PDF = (
    'From: eve@x.test\r\nSubject: with a file\r\nMIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary="in"\r\n\r\n'
    f'--in\r\nContent-Type: text/plain\r\n\r\nsee file\r\n--in\r\nContent-Type: application/pdf; name="inner.pdf"\r\n'
    f'Content-Disposition: attachment; filename="inner.pdf"\r\nContent-Transfer-Encoding: base64\r\n\r\n{_encoded(_PDF)}\r\n--in--\r\n'
)
_FWD_HEADERS = ('Content-Disposition: attachment; filename="fwd.eml"',)


@pytest.mark.parametrize(
    "forwarded",
    [
        pytest.param(_FORWARDED, id="plain"),
        pytest.param(_FORWARDED.replace("invoice", "发票").replace("hello", "你好"), id="raw-utf-8"),
        pytest.param(
            "From: eve@x.test\r\nSubject: =?UTF-8?B?5Y+R56Wo?=\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n=E4=BD=A0\r\n",
            id="encoded-word-and-quoted-printable",
        ),
        pytest.param(_FORWARDED_PDF, id="with-a-file-inside"),
        pytest.param(_FORWARDED.replace("invoice", "word " * 30), id="subject-longer-than-a-line"),
        pytest.param(_FORWARDED.replace("hello", "From me to you\r\n>From you"), id="line-that-starts-with-from"),
        pytest.param(_FORWARDED.replace("hello\r\n", "hello"), id="no-line-break-at-the-end"),
        pytest.param(_FORWARDED.replace("invoice", "in\u2028voice"), id="unicode-line-separator-in-a-header"),
        pytest.param(_FORWARDED.replace("invoice", "in\x0cvoice"), id="form-feed-in-a-header"),
        pytest.param(_FORWARDED.replace("invoice", "invoice\x0b"), id="control-character-ending-a-header"),
        pytest.param(_FORWARDED.replace("invoice", "invoice\x1cX-Next: kept"), id="control-character-before-a-header-name"),
    ],
)
def test_download_saves_an_attached_message_as_the_message_it_was(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    forwarded: str,
) -> None:
    """A mail client opens the saved ``.eml``, so it has to be the message that was sent, line breaks and raw UTF-8 included."""
    raw = _mixed(_TEXT_BODY, _attached_message(forwarded, *_FWD_HEADERS))

    run_main(email_manager, monkeypatch, conn_serving(raw), "download", "1", "--output-dir", str(tmp_path), "--filename", "fwd")

    assert json.loads(capsys.readouterr().out)["status"] == "downloaded"
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == {"fwd.eml": forwarded.encode()}


def test_the_files_inside_an_attached_message_are_listed_and_saved_on_their_own(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    raw = _mixed(_TEXT_BODY, _attached_message(_FORWARDED_PDF, *_FWD_HEADERS))

    run_main(email_manager, monkeypatch, conn_serving(raw), "read", "1")
    read = json.loads(capsys.readouterr().out)
    run_main(email_manager, monkeypatch, conn_serving(raw), "download", "1", "--output-dir", str(tmp_path))
    capsys.readouterr()

    assert [entry["filename"] for entry in read["attachments"]] == ["fwd.eml", "inner.pdf"]
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()}["inner.pdf"] == _PDF
    assert sorted(path.name for path in tmp_path.iterdir()) == ["fwd.eml", "inner.pdf"]


_ATTACHED_CONTAINER = _mixed(_TEXT_BODY).replace(
    b"MIME-Version: 1.0\r\n", b'MIME-Version: 1.0\r\nContent-Disposition: attachment; filename="c.zip"\r\n'
)


@pytest.mark.parametrize(
    ("raw", "content"),
    [
        pytest.param(_leaf(_PDF_TYPE, "Content-Disposition: attachment"), _PDF, id="a-file"),
        pytest.param(_ATTACHED_CONTAINER, None, id="a-container-attached-by-its-disposition"),
    ],
)
def test_a_part_that_holds_no_file_has_no_bytes_to_save(message: ModuleType, raw: bytes, content: bytes | None) -> None:
    stored = email.message_from_bytes(raw)

    assert message.attachment_bytes(next(message.attachment_parts(stored))) == content


@pytest.mark.parametrize(
    ("raw", "saved", "status"),
    [
        pytest.param(
            _mixed(_TEXT_BODY, _part(_PDF_TYPE, 'Content-Disposition: attachment; filename="empty.pdf"', content=b"")),
            {"empty.pdf": b""},
            "downloaded",
            id="a-file-that-is-empty",
        ),
        pytest.param(_ATTACHED_CONTAINER, {}, "no_attachments", id="a-container-that-holds-no-file"),
    ],
)
def test_download_saves_an_empty_file_and_nothing_for_a_part_that_holds_no_file(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    raw: bytes,
    saved: dict[str, bytes],
    status: str,
) -> None:
    run_main(email_manager, monkeypatch, conn_serving(raw), "download", "1", "--output-dir", str(tmp_path))

    assert json.loads(capsys.readouterr().out)["status"] == status
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == saved
