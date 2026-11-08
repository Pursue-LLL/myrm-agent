"""Payload classification: web page, text or binary file, decided in one place.

[INPUT]
None (pure stdlib: io, re, zipfile, zlib, enum)

[OUTPUT]
- PayloadKind: WEB (HTML to convert), TEXT (readable as it is), BINARY (a file for a parser).
- classify_payload: declared content type plus leading bytes -> PayloadKind.
- magic_extension: file extension from a format signature, zip containers resolved to their document type.
- zip_file_extension: which document a zip container is (docx, xlsx, pptx, epub, odf, plain zip).

[POS]
Single source of truth for "what is this payload", shared by the HTTP fetcher, the binary router, the file
parsers' format sniffing and the Wiki source loader. Pure functions over bytes and zip containers: no toolkit
imports.
"""

from __future__ import annotations

import io
import os
import re
import zipfile
import zlib
from enum import Enum, auto
from typing import IO


class PayloadKind(Enum):
    WEB = auto()
    TEXT = auto()
    BINARY = auto()


_ZIP_MIMETYPE_EXTENSIONS = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/epub+zip": ".epub",
    "application/vnd.oasis.opendocument.text": ".odt",
    "application/vnd.oasis.opendocument.spreadsheet": ".ods",
    "application/vnd.oasis.opendocument.presentation": ".odp",
}
_OOXML_DIRECTORIES = (("word/", ".docx"), ("xl/", ".xlsx"), ("ppt/", ".pptx"))
# The declared type is a short ASCII line; a hostile archive must not get a bomb-sized entry inflated for it.
_MIMETYPE_READ_LIMIT = 256
# Everything a corrupt or hostile archive can raise while its directory and first entries are read (ValueError
# covers invalid entry names and the zip-bomb overlap check).
_ZIP_READ_ERRORS = (zipfile.BadZipFile, zlib.error, EOFError, OSError, RuntimeError, NotImplementedError, ValueError)

# Formats whose leading bytes settle the question whatever the server declared. BMP is left out on purpose: its
# two-byte signature ("BM") opens ordinary text.
_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", ".pdf"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpeg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", ".doc"),
    (b"PK\x03\x04", ".zip"),
)

# WHATWG MIME sniffing: these bytes never occur in text, and only the first 1445 bytes are scanned.
_BINARY_DATA_BYTE = re.compile(rb"[\x00-\x08\x0b\x0e-\x1a\x1c-\x1f]")
_SNIFF_WINDOW = 1445
_TEXT_BOMS = (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")
# Openings that make an untyped payload a web page (WHATWG unknown-type sniffing); a tag must be followed by
# whitespace or '>'.
_HTML_PREFIX = re.compile(
    rb"\s*<(?:!doctype html|!--|html|head|body|script|iframe|h1|div|font|table|a|style|title|b|br|p)[\s>]",
    re.IGNORECASE,
)
_HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_STRUCTURED_TEXT_TYPES = frozenset(
    {"application/json", "application/xml", "application/javascript", "application/ecmascript"}
)
_STRUCTURED_TEXT_SUFFIXES = ("+json", "+xml")
_BINARY_MEDIA_PREFIXES = ("image/", "audio/", "video/", "font/")


def _zip_extension(archive: zipfile.ZipFile) -> str:
    names = archive.namelist()
    if "mimetype" in names:
        with archive.open("mimetype") as entry:
            declared = entry.read(_MIMETYPE_READ_LIMIT).decode("utf-8", errors="ignore")
        extension = _ZIP_MIMETYPE_EXTENSIONS.get(declared.strip().split(";")[0].strip())
        if extension:
            return extension
    if "[Content_Types].xml" in names:
        for directory, extension in _OOXML_DIRECTORIES:
            if any(name.startswith(directory) for name in names):
                return extension
    if "META-INF/container.xml" in names:
        return ".epub"
    if "content.xml" in names:
        return ".odt"
    return ".zip"


def zip_file_extension(source: str | os.PathLike[str] | IO[bytes]) -> str:
    """Name the document a zip container holds; ``.zip`` when it is none of the known document types.

    The declared ``mimetype`` entry wins (epub, odf, and docx written by tools that declare one), then the
    OOXML layout, then the epub and odf marker entries. An unreadable archive is still a zip: it is reported
    as ``.zip``, never as an error.
    """
    try:
        with zipfile.ZipFile(source) as archive:
            return _zip_extension(archive)
    except _ZIP_READ_ERRORS:
        return ".zip"


def _signature_extension(body: bytes) -> str | None:
    for signature, extension in _SIGNATURES:
        if body.startswith(signature):
            return extension
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return ".webp"
    if body[:5].lower() == b"{\\rtf":
        return ".rtf"
    return None


def magic_extension(body: bytes) -> str | None:
    """File extension of a payload whose leading bytes carry a format signature, else ``None``."""
    extension = _signature_extension(body)
    if extension == ".zip":
        return zip_file_extension(io.BytesIO(body))
    return extension


def _is_declared_text(declared: str) -> bool:
    return (
        declared.startswith("text/")
        or declared in _STRUCTURED_TEXT_TYPES
        or declared.endswith(_STRUCTURED_TEXT_SUFFIXES)
    )


def classify_payload(content_type: str | None, body: bytes) -> PayloadKind:
    """Decide web page, text or binary file from the declared type and the leading bytes.

    A format signature beats any declared type. A declared HTML type is a web page and a declared text type
    (``text/*``, JSON, XML, JavaScript) is text, both trusted; a declared image, audio, video or font type is
    binary. Anything else (missing, generic, unknown) is sniffed the way browsers do: a text byte-order mark
    means text, a binary-data byte in the first 1445 bytes means binary, an HTML opening means a web page.
    """
    if _signature_extension(body) is not None:
        return PayloadKind.BINARY
    declared = (content_type or "").split(";")[0].strip().lower()
    if declared in _HTML_TYPES:
        return PayloadKind.WEB
    if _is_declared_text(declared):
        return PayloadKind.TEXT
    if declared.startswith(_BINARY_MEDIA_PREFIXES):
        return PayloadKind.BINARY
    window = body[:_SNIFF_WINDOW]
    if not window.startswith(_TEXT_BOMS) and _BINARY_DATA_BYTE.search(window):
        return PayloadKind.BINARY
    if _HTML_PREFIX.match(window.removeprefix(b"\xef\xbb\xbf")):
        return PayloadKind.WEB
    return PayloadKind.TEXT
