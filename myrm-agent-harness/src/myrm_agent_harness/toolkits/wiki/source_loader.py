"""Source loading for Wiki ingestion: the readable text of a web page or a local file, or a reason it has none.

[INPUT]
- toolkits.web_fetch::web_fetch_tools (POS: Global FetchEngine singleton — SSRF-guarded multi-tier fetch, YouTube/Bilibili subtitles)
- toolkits.file_parsers::get_parser, is_supported (POS: Document parsers for PDF, Office, images and more)
- toolkits.file_parsers::TextDecodingError, decode_text_bytes (POS: Text bytes to str: UTF-8, Unicode BOM or an identifiable legacy encoding such as GBK)
- utils.content_sniff::PayloadKind, classify_payload (POS: Tells a binary file from text)

[OUTPUT]
- SourceLoadError: a source that cannot become readable text; the message names the cause and is safe to show
- fetch_url_markdown: the readable markdown of a URL
- read_local_file: the text of a local file
- looks_like_local_path: whether an ingestion source string names an existing local file

[POS]
Turns an ingestion source into text for the raw/ layer. It never invents content: a page that could not be
fetched, a file no parser supports, bytes that are not text and text in an encoding that cannot be identified raise
SourceLoadError, so nothing but real text is written to the knowledge base and compiled.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from myrm_agent_harness.utils.content_sniff import PayloadKind, classify_payload

# Longer strings are pasted text, never a path, and are not worth a filesystem lookup.
_MAX_PATH_CHARS = 260
# Enough leading bytes to tell a binary file from text without reading a large file into memory first.
_SNIFF_BYTES = 8192


class SourceLoadError(Exception):
    """The source could not be turned into readable text."""


def looks_like_local_path(source: str) -> bool:
    """Whether an ingestion source names an existing local file rather than a URL or raw text."""
    # A blank string is no path: Path("") is the current directory, which always exists.
    if not source.strip() or source.startswith(("http://", "https://")):
        return False
    return len(source) < _MAX_PATH_CHARS and "\n" not in source and Path(source).exists()


async def fetch_url_markdown(url: str) -> str:
    """Fetch a URL through the FetchEngine (SSRF guard, tier degradation, subtitle extractors).

    A page with nothing readable raises SourceLoadError, and so does a URL the SSRF guard blocks: the engine
    answers a blocked, timed-out or unreachable URL with no document. An unexpected engine failure propagates.
    """
    from myrm_agent_harness.toolkits.web_fetch import web_fetch_tools

    doc = await web_fetch_tools.crawl(url)
    if doc is None or not doc.page_content.strip():
        raise SourceLoadError(f"No readable content could be fetched from {url}")
    return doc.page_content


def _undecodable(path: Path) -> SourceLoadError:
    return SourceLoadError(
        f"{path.name} is not UTF-8 text and its encoding could not be identified reliably; "
        "save it as UTF-8 and ingest it again"
    )


def _read_text_file(path: Path) -> str:
    from myrm_agent_harness.toolkits.file_parsers import TextDecodingError, decode_text_bytes

    try:
        with path.open("rb") as handle:
            if classify_payload(None, handle.read(_SNIFF_BYTES)) is PayloadKind.BINARY:
                raise SourceLoadError(f"{path.name} is a binary file that no parser supports")
            handle.seek(0)
            data = handle.read()
    except OSError as exc:
        raise SourceLoadError(f"{path.name} could not be read") from exc
    try:
        return decode_text_bytes(data)
    except TextDecodingError as exc:
        raise _undecodable(path) from exc


async def read_local_file(path: Path) -> str:
    """The text of a local file: parsed when a parser supports its format, read as text otherwise.

    Text is UTF-8, UTF-16/32 with a byte-order mark, or a legacy encoding such as GBK that can be identified from
    the bytes. A binary file no parser supports and text whose encoding cannot be identified reliably are refused
    instead of being decoded into replacement characters, which would be compiled into the knowledge base as garbage.
    """
    from myrm_agent_harness.toolkits.file_parsers import TextDecodingError, get_parser, is_supported

    if not await asyncio.to_thread(path.is_file):
        raise SourceLoadError(f"{path.name} is not a regular file")
    if await asyncio.to_thread(is_supported, str(path)):
        try:
            text = await get_parser(str(path)).parse(str(path))
        except TextDecodingError as exc:
            raise _undecodable(path) from exc
        if not text.strip():
            raise SourceLoadError(f"The parser found no text in {path.name}")
        return text
    text = await asyncio.to_thread(_read_text_file, path)
    if not text.strip():
        raise SourceLoadError(f"{path.name} is empty")
    return text
