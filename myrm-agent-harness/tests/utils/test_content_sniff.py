"""Payload classification: one rule set decides web page, text or binary file."""

from __future__ import annotations

import io
import random
import tracemalloc
import zipfile
from pathlib import Path

import pytest

from myrm_agent_harness.utils.content_sniff import PayloadKind, classify_payload, magic_extension, zip_file_extension

WEB, TEXT, BINARY = PayloadKind.WEB, PayloadKind.TEXT, PayloadKind.BINARY

HTML_PAGE = b"<!DOCTYPE html><html><head><title>t</title></head><body><p>hello</p></body></html>"
PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 16
EXE = b"MZ\x90\x00" + bytes(range(256)) * 4


# A fixed timestamp keeps the archive bytes, and so the parametrized test ids, identical in every pytest-xdist worker.
_ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            member = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
            member.external_attr = 0o600 << 16
            archive.writestr(member, data)
    return buffer.getvalue()


OOXML = {"[Content_Types].xml": b"<Types/>"}
DOCX = _zip({**OOXML, "word/document.xml": b"<w/>"})


@pytest.mark.parametrize(
    ("content_type", "body", "expected"),
    [
        # declared web pages
        ("text/html; charset=utf-8", HTML_PAGE, WEB),
        ("application/xhtml+xml", HTML_PAGE, WEB),
        ("TEXT/HTML", b"", WEB),
        # declared text is trusted, whatever it looks like
        ("text/plain; charset=utf-8", b"hello\nworld\n", TEXT),
        ("text/markdown", b"# Title\n\n<b>bold</b>\n", TEXT),
        ("text/csv", b"a,b\n1,2\n", TEXT),
        ("text/plain", b"<html>shown as source</html>", TEXT),
        ("text/plain; charset=utf-16", "hello".encode("utf-16-le"), TEXT),
        ("application/json", b'{"a": 1}', TEXT),
        ("application/ld+json", b'{"@context": "x"}', TEXT),
        ("application/vnd.api+json", b'{"data": []}', TEXT),
        ("application/xml", b"<a/>", TEXT),
        ("application/rss+xml; charset=UTF-8", b"<rss/>", TEXT),
        ("application/atom+xml", b"<feed/>", TEXT),
        ("image/svg+xml", b"<svg/>", TEXT),
        ("application/javascript", b"var a = 1;", TEXT),
        # declared media is a file, even without a signature
        ("image/png", b"not really a png", BINARY),
        ("audio/mpeg", b"ID3", BINARY),
        ("video/mp4", b"\x00\x00\x00\x18ftypmp42", BINARY),
        ("font/woff2", b"wOF2", BINARY),
        # a format signature beats any declared type
        ("application/pdf", PDF, BINARY),
        ("text/html", PDF, BINARY),
        ("text/plain", PDF, BINARY),
        (None, PDF, BINARY),
        ("application/octet-stream", PNG, BINARY),
        ("text/html", DOCX, BINARY),
        # generic or missing types are sniffed like a browser does
        (None, HTML_PAGE, WEB),
        ("application/octet-stream", b"  \n<html><body>x</body></html>", WEB),
        (None, b"<!-- note --><div>x</div>", WEB),
        (None, b"\xef\xbb\xbf<!doctype HTML><p>x</p>", WEB),
        (None, b"<abbr>not an opening tag</abbr>", TEXT),
        (None, b'<?xml version="1.0"?><root/>', TEXT),
        ("application/octet-stream", b"a,b\n1,2\n", TEXT),
        (None, b"", TEXT),
        (None, EXE, BINARY),
        ("application/octet-stream", b"GZ\x00\x01binary", BINARY),
        (None, b"\xff\xfeh\x00i\x00", TEXT),
        (None, b"\xef\xbb\xbfplain text with a BOM", TEXT),
        (None, b"\x1b[31mcoloured log line\x1b[0m\n", TEXT),
    ],
)
def test_classify_payload(content_type: str | None, body: bytes, expected: PayloadKind) -> None:
    assert classify_payload(content_type, body) is expected


def test_binary_data_byte_is_only_looked_for_inside_the_sniff_window() -> None:
    assert classify_payload(None, b"a" * 1444 + b"\x00") is BINARY
    assert classify_payload(None, b"a" * 1445 + b"\x00") is TEXT


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (PDF, ".pdf"),
        (PNG, ".png"),
        (b"\xff\xd8\xff\xe0" + b"\x00" * 16, ".jpeg"),
        (b"GIF87a" + b"\x00" * 16, ".gif"),
        (b"GIF89a" + b"\x00" * 16, ".gif"),
        (b"RIFF\x24\x00\x00\x00WEBPVP8 ", ".webp"),
        (b"{\\rtf1\\ansi hello}", ".rtf"),
        (b"{\\RTF1\\ansi hello}", ".rtf"),
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 16, ".doc"),
        (_zip({"readme.txt": b"hello"}), ".zip"),
        (DOCX, ".docx"),
        # not signatures
        (b"RIFF\x24\x00\x00\x00WAVEfmt ", None),
        (b"BM25 is a ranking function used by search engines", None),
        (b"\x89PNG", None),
        (b"plain text", None),
        (b"", None),
    ],
)
def test_magic_extension(body: bytes, expected: str | None) -> None:
    assert magic_extension(body) == expected


def test_unreadable_zip_container_is_still_a_zip() -> None:
    assert magic_extension(b"PK\x03\x04garbage") == ".zip"


@pytest.mark.parametrize(
    ("entries", "expected"),
    [
        ({**OOXML, "word/document.xml": b"<w/>"}, ".docx"),
        ({**OOXML, "xl/workbook.xml": b"<x/>"}, ".xlsx"),
        ({**OOXML, "ppt/presentation.xml": b"<p/>"}, ".pptx"),
        ({"mimetype": b"application/epub+zip", "META-INF/container.xml": b"<c/>"}, ".epub"),
        ({"META-INF/container.xml": b"<c/>"}, ".epub"),
        ({"mimetype": b"application/vnd.oasis.opendocument.text", "content.xml": b"<o/>"}, ".odt"),
        ({"mimetype": b"application/vnd.oasis.opendocument.spreadsheet", "content.xml": b"<o/>"}, ".ods"),
        ({"mimetype": b"application/vnd.oasis.opendocument.presentation; charset=x\n"}, ".odp"),
        ({"mimetype": b"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}, ".docx"),
        ({"content.xml": b"<o/>"}, ".odt"),
        # a layout without the OOXML content-types part is no Office document
        ({"word/document.xml": b"<w/>"}, ".zip"),
        ({"mimetype": b"text/plain", "readme.txt": b"hello"}, ".zip"),
        ({"readme.txt": b"hello"}, ".zip"),
    ],
)
def test_zip_file_extension(entries: dict[str, bytes], expected: str) -> None:
    assert zip_file_extension(io.BytesIO(_zip(entries))) == expected


def test_zip_file_extension_reads_a_path(tmp_path: Path) -> None:
    path = tmp_path / "upload.bin"
    path.write_bytes(DOCX)
    assert zip_file_extension(path) == ".docx"
    assert zip_file_extension(tmp_path / "missing.zip") == ".zip"


def _invalid_utf8_entry_name_archive() -> bytes:
    """An archive whose entry name is flagged UTF-8 but is not: the zip module raises UnicodeDecodeError."""
    raw = _zip({"aaaa": b"x"}).replace(b"aaaa", b"\xff\xfe\xfd\xfc")
    patched = bytearray(raw)
    utf8_flag = 0x08  # bit 11 of the general purpose flags, in the high byte
    patched[7] |= utf8_flag
    central = patched.index(b"PK\x01\x02")
    patched[central + 9] |= utf8_flag
    return bytes(patched)


def test_archive_that_makes_the_zip_module_raise_is_still_a_zip() -> None:
    hostile = _invalid_utf8_entry_name_archive()
    with pytest.raises(UnicodeDecodeError):
        zipfile.ZipFile(io.BytesIO(hostile))
    assert magic_extension(hostile) == ".zip"


def test_corrupted_archives_never_raise() -> None:
    rng = random.Random(20261107)
    for base in (DOCX, _zip({"mimetype": b"application/epub+zip", "META-INF/container.xml": b"<c/>"})):
        for _ in range(1500):
            data = bytearray(base)
            for _ in range(rng.randint(1, 8)):
                data[rng.randrange(len(data))] = rng.randrange(256)
            assert magic_extension(bytes(data[: rng.randrange(8, len(data) + 1)])) in {".docx", ".epub", ".zip", None}


def test_declared_type_entry_is_read_with_a_bound() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", b"A" * (50 * 1024 * 1024))
    bomb = buffer.getvalue()

    tracemalloc.start()
    try:
        extension = zip_file_extension(io.BytesIO(bomb))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert extension == ".zip"
    assert peak < 5 * 1024 * 1024
