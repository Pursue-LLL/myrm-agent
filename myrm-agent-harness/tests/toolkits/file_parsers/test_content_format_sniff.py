"""Tests for content-based file format sniffing."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.file_parsers import get_parser, is_supported
from myrm_agent_harness.toolkits.file_parsers.content_format_sniff import (
    sniff_content_format,
    sniff_content_format_from_bytes,
)
from myrm_agent_harness.toolkits.file_parsers.csv_parser import CsvParser
from myrm_agent_harness.toolkits.file_parsers.rtf_parser import RtfParser


def test_sniff_pdf_from_mislabeled_path(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_bytes(b"%PDF-1.4 fake pdf body")
    assert sniff_content_format(target) == ".pdf"
    assert is_supported(str(target)) is True
    assert isinstance(get_parser(str(target)), object)


def test_sniff_rtf(tmp_path: Path) -> None:
    target = tmp_path / "upload.bin"
    target.write_text("{\\rtf1\\ansi Hello RTF}", encoding="utf-8")
    assert sniff_content_format(target) == ".rtf"
    assert isinstance(get_parser(str(target)), RtfParser)


def test_sniff_csv_text(tmp_path: Path) -> None:
    target = tmp_path / "data.bin"
    target.write_text("name,score\nalice,1\nbob,2\n", encoding="utf-8")
    assert sniff_content_format(target) == ".csv"
    assert isinstance(get_parser(str(target)), CsvParser)


def test_sniff_epub_mimetype(tmp_path: Path) -> None:
    target = tmp_path / "book.dat"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("chapter.xhtml", "<html><body><p>Hello EPUB</p></body></html>")
    assert sniff_content_format(target) == ".epub"


def _zip_payload(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


ZIP_FORMATS = [
    pytest.param({"[Content_Types].xml": "<Types/>", "word/document.xml": "<w/>"}, ".docx", id="docx"),
    pytest.param({"[Content_Types].xml": "<Types/>", "xl/workbook.xml": "<x/>"}, ".xlsx", id="xlsx"),
    pytest.param({"[Content_Types].xml": "<Types/>", "ppt/presentation.xml": "<p/>"}, ".pptx", id="pptx"),
    pytest.param({"META-INF/container.xml": "<c/>"}, ".epub", id="epub"),
    pytest.param({"mimetype": "application/vnd.oasis.opendocument.spreadsheet"}, ".ods", id="ods"),
    pytest.param({"content.xml": "<o/>"}, ".odt", id="odt"),
    # a layout that holds both an Office and an OpenDocument marker is the same format on both sniffing paths
    pytest.param(
        {"[Content_Types].xml": "<Types/>", "word/document.xml": "<w/>", "content.xml": "<o/>"}, ".docx", id="mixed"
    ),
    pytest.param({"readme.txt": "hello"}, None, id="plain-zip"),
]


@pytest.mark.parametrize(("entries", "expected"), ZIP_FORMATS)
def test_zip_container_is_named_the_same_from_a_path_and_from_bytes(
    tmp_path: Path, entries: dict[str, str], expected: str | None
) -> None:
    payload = _zip_payload(entries)
    target = tmp_path / "upload.bin"
    target.write_bytes(payload)

    assert sniff_content_format(target) == expected
    assert sniff_content_format_from_bytes(payload) == expected


def test_unreadable_zip_container_names_no_format(tmp_path: Path) -> None:
    payload = b"PK\x03\x04" + b"not a real archive" * 4
    target = tmp_path / "broken.bin"
    target.write_bytes(payload)

    assert sniff_content_format(target) is None
    assert sniff_content_format_from_bytes(payload) is None


@pytest.mark.asyncio
async def test_csv_parser_renders_markdown_table(tmp_path: Path) -> None:
    target = tmp_path / "grid.csv"
    target.write_text("h1,h2\nv1,v2\n", encoding="utf-8")
    parser = CsvParser()
    text = await parser.parse(str(target))
    assert "| h1 | h2 |" in text
    assert "| v1 | v2 |" in text
