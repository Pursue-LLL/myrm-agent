"""Shared fakes of the PDF reader tests: an extraction result, its config and a page image."""

from __future__ import annotations

from dataclasses import dataclass, field


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
    """Mirrors `PDFExtractConfig` defaults so the ingest trigger sees real values."""

    def __init__(self, max_pages: int = 500, extract_embedded_images: bool = True) -> None:
        self.max_pages = max_pages
        self.extract_embedded_images = extract_embedded_images
