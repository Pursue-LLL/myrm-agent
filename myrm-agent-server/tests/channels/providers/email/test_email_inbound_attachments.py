"""Attachments of an incoming mail: which parts count as attached, what each is called, where it is saved and that a message
that fails leaves no file behind.

Each case hands the raw bytes of a message to the real parser. The disposition, the file name and the saved path all depend
on what the standard library returns for those bytes (an encoded word comes back undecoded, raw UTF-8 comes back as a
``Header``), which a hand-built message object would not reproduce.
"""

from __future__ import annotations

import base64
import errno
import re
import tempfile
import urllib.parse
from email.header import Header
from pathlib import Path
from typing import IO, Self

import pytest

from app.channels.providers.email import inbound
from app.channels.types import InboundMessage
from tests.channels.providers.email.email_channel_factory import (
    make_channel,
    parse_inbound,
    raw_mail_with_attachments,
    raw_message,
)

_PDF = b"%PDF-1.4 stand-in"
_NAME = "发票.docx"
# What a saved attachment may be called: the temp file's own random name and, at most, a plain extension.
_SAVED_NAME = re.compile(r"email_att_\w{8}(\.[A-Za-z0-9]{1,16})?")


@pytest.fixture(autouse=True)
def _save_into_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))


def _part(content_type: bytes, headers: bytes = b"") -> bytes:
    """A MIME part holding the PDF stand-in; *headers* are extra header lines, each ending in CRLF."""
    return (
        b"Content-Type: "
        + content_type
        + b"\r\n"
        + headers
        + b"Content-Transfer-Encoding: base64\r\n\r\n"
        + base64.encodebytes(_PDF)
    )


def _attached(file_name: bytes, content_type: bytes = b"application/octet-stream") -> bytes:
    """A part whose ``Content-Disposition`` is ``attachment`` with *file_name* spelled as given (``filename=...``)."""
    return _part(content_type, b"Content-Disposition: attachment; " + file_name + b"\r\n")


def _mixed(*parts: bytes) -> InboundMessage:
    """A message with a text body followed by *parts*, as the channel reads it."""
    body = (
        b"--b\r\nContent-Type: text/plain\r\n\r\nSee attached\r\n"
        + b"".join(b"--b\r\n" + part + b"\r\n" for part in parts)
        + b"--b--\r\n"
    )
    return parse_inbound(raw_message(body=body, content_type=b"multipart/mixed; boundary=b"))


def _quoted(name: str) -> bytes:
    return b'filename="' + name.encode() + b'"'


class TestWhichPartsAreAttached:
    @pytest.mark.parametrize(
        "disposition",
        [b'attachment; filename="a.pdf"', b'ATTACHMENT; filename="a.pdf"', b'inline; filename="a.pdf"'],
        ids=["attachment", "uppercase", "inline"],
    )
    def test_a_named_part_is_attached_whatever_the_case_or_the_disposition(self, disposition: bytes) -> None:
        part = _part(b"application/pdf", b"Content-Disposition: " + disposition + b"\r\n")

        assert [attachment.filename for attachment in _mixed(part).media] == ["a.pdf"]

    def test_a_part_named_only_by_its_content_type_is_attached(self) -> None:
        assert [attachment.filename for attachment in _mixed(_part(b'application/pdf; name="a.pdf"')).media] == ["a.pdf"]

    @pytest.mark.parametrize("content_type", [b"text/plain", b"application/pdf"], ids=["text", "binary"])
    def test_an_attachment_disposition_counts_for_any_part_in_any_case(self, content_type: bytes) -> None:
        """Without a file name the disposition is all there is to go by."""
        [attachment] = _mixed(_part(content_type, b"Content-Disposition: ATTACHMENT\r\n")).media

        assert attachment.filename == "attachment"

    def test_an_inline_part_that_names_no_file_is_not_attached(self) -> None:
        assert _mixed(_part(b"image/png", b"Content-Disposition: inline\r\n")).media == ()

    @pytest.mark.parametrize(
        ("url_id", "content_id"),
        [
            (b"logo@example.com", b"logo@example.com"),
            (b"logo%40example.com", b"logo@example.com"),
            (b"a%40b.example", b"a%40b.example"),
        ],
        ids=["as-written", "url-escaped", "escape-in-the-id"],
    )
    def test_an_image_the_html_embeds_by_content_id_is_not_attached(self, url_id: bytes, content_id: bytes) -> None:
        html = b'Content-Type: text/html; charset=utf-8\r\n\r\n<p>Hi</p><img src="cid:' + url_id + b'">'
        logo = _part(b"image/png", b"Content-ID: <" + content_id + b'>\r\nContent-Disposition: inline; filename="logo.png"\r\n')

        assert _mixed(html, logo).media == ()

    def test_a_text_part_that_names_itself_is_not_an_attachment(self) -> None:
        assert _mixed(b'Content-Type: text/plain; name="note.txt"\r\n\r\nthe note').media == ()

    def test_a_message_that_is_itself_the_attachment_is_attached_and_not_read_as_text(self) -> None:
        raw = raw_message(
            {"Content-Transfer-Encoding": b"base64", "Content-Disposition": b'attachment; filename="scan.pdf"'},
            body=base64.encodebytes(_PDF),
            content_type=b"application/pdf",
        )

        result = parse_inbound(raw)

        assert [attachment.filename for attachment in result.media] == ["scan.pdf"]
        assert result.content == ""

    def test_a_single_text_part_is_the_body_whatever_its_disposition_says(self) -> None:
        raw = raw_message(
            {"Content-Disposition": b'attachment; filename="notes.txt"'},
            body=b"the notes",
            content_type=b"text/plain; charset=utf-8",
        )

        result = parse_inbound(raw)

        assert result.media == ()
        assert result.content == "the notes"


class TestAttachmentName:
    @pytest.mark.parametrize(
        "file_name",
        [
            b'filename="' + Header(_NAME, "utf-8").encode().encode() + b'"',
            _quoted(_NAME),
            b"filename*=utf-8''" + urllib.parse.quote(_NAME).encode(),
        ],
        ids=["rfc2047", "raw-utf8", "rfc2231"],
    )
    def test_a_non_ascii_name_is_read_whatever_its_spelling(self, file_name: bytes) -> None:
        [attachment] = _mixed(_attached(file_name)).media

        assert attachment.filename == _NAME
        assert Path(attachment.path or "").suffix == ".docx"

    def test_a_part_that_names_no_file_is_called_attachment(self) -> None:
        [attachment] = _mixed(_part(b"application/pdf", b"Content-Disposition: attachment\r\n")).media

        assert attachment.filename == "attachment"


class TestSavedPath:
    @pytest.mark.parametrize(
        "name",
        ["a.pdf;touch PWNED", "a.$(id)", "a.`id`", "a.p df", "a.发票", "a." + "x" * 300],
        ids=["shell-list", "substitution", "backticks", "space", "non-ascii", "too-long"],
    )
    def test_only_a_plain_extension_of_the_senders_name_reaches_the_saved_path(self, name: str) -> None:
        """The sender chooses the name; it is shown as sent, but the file system, a shell and a prompt see no part of it."""
        [attachment] = _mixed(_attached(_quoted(name))).media

        assert attachment.filename == name
        assert attachment.path
        assert _SAVED_NAME.fullmatch(Path(attachment.path).name)

    def test_a_plain_extension_is_kept_so_that_extraction_can_route_by_it(self) -> None:
        [attachment] = _mixed(_attached(_quoted("Q3 report.PDF"), b"application/pdf")).media

        assert Path(attachment.path or "").suffix == ".PDF"


class _FailingFile:
    """A temporary file that is out of room: writing to it raises ``ENOSPC``."""

    def __init__(self, file: IO[bytes]) -> None:
        self._file = file
        self.name = file.name

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._file.close()

    def write(self, data: bytes) -> int:
        raise OSError(errno.ENOSPC, "No space left on device")


class _FullDisk:
    """Stands in for ``tempfile.NamedTemporaryFile``: the *nth* file it hands out cannot be written to, the others are real."""

    def __init__(self, nth: int) -> None:
        self._nth = nth
        self._handed_out = 0
        self._real = tempfile.NamedTemporaryFile

    def __call__(self, *, delete: bool, prefix: str, suffix: str) -> IO[bytes] | _FailingFile:
        self._handed_out += 1
        file = self._real(delete=delete, prefix=prefix, suffix=suffix)
        return _FailingFile(file) if self._handed_out == self._nth else file


class TestAFailedMessageLeavesNoFiles:
    """A message that fails is read again, so a file it wrote the first time would be written a second time."""

    @pytest.mark.parametrize("nth", [1, 3], ids=["the-first-file", "the-third-file"])
    def test_a_write_that_fails_removes_the_failed_file_and_the_ones_written_before_it(
        self, nth: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tempfile, "NamedTemporaryFile", _FullDisk(nth))

        with pytest.raises(OSError, match="No space left"):
            make_channel()._parse_email(raw_mail_with_attachments(1, "a.pdf", "b.pdf", "c.pdf"), uid=1)

        assert list(tmp_path.iterdir()) == []

    def test_the_retry_leaves_the_files_of_the_message_alone(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        raw = raw_mail_with_attachments(1, "a.pdf", "b.pdf", "c.pdf")
        channel = make_channel()
        monkeypatch.setattr(tempfile, "NamedTemporaryFile", _FullDisk(3))
        with pytest.raises(OSError, match="No space left"):
            channel._parse_email(raw, uid=1)

        retried = channel._parse_email(raw, uid=1)

        assert retried is not None
        assert len(retried.media) == 3
        assert {Path(str(attachment.path)) for attachment in retried.media} == set(tmp_path.iterdir())

    def test_a_failure_after_the_attachments_were_found_writes_none_of_them(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refuse(html: str) -> str:
            raise RuntimeError("converter failed")

        monkeypatch.setattr(inbound, "_html_to_markdown", refuse)

        with pytest.raises(RuntimeError, match="converter failed"):
            make_channel()._parse_email(raw_mail_with_attachments(1, "a.pdf", "b.pdf", body_subtype="html"), uid=1)

        assert list(tmp_path.iterdir()) == []
