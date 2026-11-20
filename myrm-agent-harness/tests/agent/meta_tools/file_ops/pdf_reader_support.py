"""Shared fakes of the PDF reader tests: an extraction result, its config, a page image and a read driver."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, patch

from langchain_core.messages.content import ContentBlock

from myrm_agent_harness.agent.meta_tools.file_ops.utils.pdf_reader import read_pdf_as_content_blocks

_READER = "myrm_agent_harness.agent.meta_tools.file_ops.utils.pdf_reader"
_EXTRACTOR = "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor"


@dataclass
class FakeImage:
    data: str = "base64data"
    mime_type: str = "image/png"
    page_number: int = 0


@dataclass
class FakePDFResult:
    text: str
    page_count: int
    images: list[FakeImage] = field(default_factory=list)
    parsed_pages: int = 0
    # Pages the text layer could not read; defaults to none so existing cases keep meaning
    # "the text covers everything it delivered".
    pages_without_text: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        # A result that says nothing about its coverage delivered every page.
        if self.parsed_pages == 0:
            self.parsed_pages = self.page_count


class FakeConfig:
    """Mirrors `PDFExtractConfig` defaults."""

    def __init__(self, max_pages: int = 500, extract_embedded_images: bool = True) -> None:
        self.max_pages = max_pages
        self.extract_embedded_images = extract_embedded_images


async def read_pdf_with_extraction(result: FakePDFResult, *, supports_vision: bool = False) -> str | list[ContentBlock]:
    """Read a PDF through ``read_pdf_as_content_blocks`` while the extractor returns ``result``."""
    executor = AsyncMock()
    executor.read_file_bytes = AsyncMock(return_value=b"bytes")
    with (
        patch(f"{_READER}._write_to_temp", new_callable=AsyncMock, return_value="/tmp/t.pdf"),
        patch("os.unlink"),
        patch(f"{_EXTRACTOR}.extract_pdf_content", new_callable=AsyncMock, return_value=result),
        patch(f"{_EXTRACTOR}.PDFExtractConfig", FakeConfig),
    ):
        return await read_pdf_as_content_blocks("/tmp/t.pdf", executor, supports_vision)
