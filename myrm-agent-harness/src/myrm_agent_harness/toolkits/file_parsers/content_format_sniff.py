"""Content-based file format sniffing for mislabeled uploads.

[INPUT]
- File path or initial byte prefix
- utils.content_sniff::zip_file_extension (POS: Names the document a zip container holds)

[OUTPUT]
- Normalized extension (e.g. ".pdf") when content signature matches

[POS]
Shared by file_parsers.get_parser and wiki/raw ingest routing.
"""

from __future__ import annotations

import io
from pathlib import Path

from myrm_agent_harness.utils.content_sniff import zip_file_extension

_MAX_SNIFF_BYTES = 8192


def sniff_content_format(file_path: str | Path) -> str | None:
    """Return a supported extension inferred from file content, or None."""
    path = Path(file_path)
    if not path.is_file():
        return None

    prefix = _read_prefix(path)
    if not prefix:
        return None

    if prefix.startswith(b"%PDF"):
        return ".pdf"

    if prefix.startswith(b"{\\rtf") or prefix.startswith(b"{\\RTF"):
        return ".rtf"

    if prefix.startswith(b"PK\x03\x04"):
        return _document_extension(zip_file_extension(path))

    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"

    if prefix[:3] == b"\xff\xd8\xff":
        return ".jpg"

    if prefix.startswith(b"RIFF") and b"WEBP" in prefix[:16]:
        return ".webp"

    if _looks_like_csv_text(prefix):
        return ".csv"

    return None


def _read_prefix(path: Path) -> bytes:
    try:
        with path.open("rb") as handle:
            return handle.read(_MAX_SNIFF_BYTES)
    except OSError:
        return b""


def sniff_content_format_from_bytes(content: bytes) -> str | None:
    """Sniff format from an in-memory byte prefix."""
    if not content:
        return None
    prefix = content[:_MAX_SNIFF_BYTES]
    if prefix.startswith(b"%PDF"):
        return ".pdf"
    if prefix.startswith(b"{\\rtf") or prefix.startswith(b"{\\RTF"):
        return ".rtf"
    if prefix.startswith(b"PK\x03\x04"):
        return _document_extension(zip_file_extension(io.BytesIO(content)))
    if _looks_like_csv_text(prefix):
        return ".csv"
    return None


def _document_extension(zip_extension: str) -> str | None:
    """A plain zip is no document any parser reads."""
    return None if zip_extension == ".zip" else zip_extension


def _looks_like_csv_text(prefix: bytes) -> bool:
    try:
        sample = prefix.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if "\x00" in sample:
        return False
    lines = [line for line in sample.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    comma_lines = sum(1 for line in lines[:20] if "," in line)
    return comma_lines >= 2
