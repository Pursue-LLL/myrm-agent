"""PDF file reader for file_read_tool

Uses pdf_content_extractor for unified smart extraction:
- Text-first via pdfplumber (with table extraction)
- Image fallback via pypdfium2 when text is sparse
- Returns LangChain content blocks for multimodal models, plain text otherwise
- A document longer than PDF_READ_PAGE_WINDOW pages is read through that window and
  says so, instead of being silently truncated

[INPUT]
- toolkits.file_parsers.pdf.pdf_content_extractor::PDFExtractConfig (POS: Smart PDF extraction orchestrator. Auto-selects Text/Hybrid(embedded image)/Image(full-page render fallback) strategy; scanned PDFs (sparse text) get best-effort OCR fallback via RapidOCR so text-only consumers still get readable text. Supports Table Encapsulation to prevent RAG chunking from splitting tables, using L0 summaries to ensure retrieval accuracy.)
- toolkits.file_parsers.pdf.pdf::pages_with_text (POS: pdfplumber-based PDF parser orchestrator: page parsing (sequential/parallel), heading composition, cross-page stitching and text/table merging, with an optional physical ``max_pages`` slice. Owns the page-marker format and the matching helper that tells real content from markers.)
- toolkits.llms.vision.fallback_engine::create_vision_fallback_engine (POS: Auxiliary vision chain builder; describes delivered page images as text for text-only models.)
- toolkits.code_execution.executors.base::CodeExecutor (POS: Code executor base classes.)

[OUTPUT]
- is_pdf_path: Detect if path is a PDF file
- read_pdf_as_content_blocks: Read PDF and return smart-extracted content (supports parse_mode="structure" for structural heading outlines).

[POS]
PDF file reader for file_read_tool. Delivery mirrors the sibling readers: a
vision-capable model receives the page images as blocks, a text-only model with a
vision fallback configured receives them as text descriptions, and only when no
vision route exists does it degrade to plain text. A document longer than
PDF_READ_PAGE_WINDOW pages is read through that window and ends with one hint that
states how many pages were read (the pages its text still reaches when the character
cap cuts it short), that file_read cannot open the rest, and that the structure
outline lists what the rest holds. Reading never ingests anything into a knowledge
base.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from langchain_core.messages.content import ContentBlock, create_image_block, create_text_block

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.code_execution.executors.base import CodeExecutor
    from myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor import PDFExtractResult

logger = logging.getLogger(__name__)

PDF_EXTENSIONS: frozenset[str] = frozenset({".pdf"})

_FALLBACK_MAX_CHARS = 100_000

# Pages one read delivers; a longer document is read through this window.
PDF_READ_PAGE_WINDOW = 20

# Bounds the structure outline injected into context for very long documents.
STRUCTURE_OUTLINE_MAX_ENTRIES = 200


def is_pdf_path(path: str) -> bool:
    """Detect if path is a PDF file"""
    suffix = PurePosixPath(path).suffix.lower()
    return suffix in PDF_EXTENSIONS


async def _write_to_temp(raw_bytes: bytes) -> str:
    """Write PDF bytes to a temp file and return the temp path.

    Needed because pdf_content_extractor requires a filesystem path.
    """

    def _write() -> str:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp.flush()
            return tmp.name

    return await asyncio.to_thread(_write)


async def read_pdf_as_content_blocks(
    path: str,
    executor: CodeExecutor,
    supports_vision: bool,
    *,
    vision_fallback_model_cfg: object | None = None,
    vision_fallback_model_cfgs: object | None = None,
    parse_mode: str | None = None,
) -> str | list[ContentBlock]:
    """Read PDF and return smart-extracted content or structural outline.

    A vision-capable model receives the delivered page images as content blocks. A
    text-only model with an auxiliary vision chain configured receives the same pages
    as text descriptions, so scanned pages are never dropped silently just because the
    primary model cannot see images.

    When parse_mode='structure', extracts the document bookmarks and chapter
    hierarchy without full text extraction or OCR, enabling progressive disclosure.
    A document longer than PDF_READ_PAGE_WINDOW pages is read through that window and
    its result ends with a ``[Partial Read]`` hint.
    """
    try:
        raw_bytes = await executor.read_file_bytes(path)
    except FileNotFoundError:
        raise
    except Exception as e:
        logger.warning("Failed to read PDF bytes: %s, error: %s", path, e)
        return f"[PDF file: {path}] (Failed to read)"

    if parse_mode == "structure":
        tmp_path = await _write_to_temp(raw_bytes)
        try:
            from myrm_agent_harness.toolkits.file_parsers.pdf.pdf import PDFPlumberParser

            parser = PDFPlumberParser(extract_tables=False)
            res = await asyncio.to_thread(parser.parse_sync, tmp_path)
            headings = res.headings
            page_count = res.metadata.get("page_count", 0)

            outline_lines = [f"[DOCUMENT STRUCTURE OUTLINE: {PurePosixPath(path).name} (Total Pages: {page_count})]:"]
            if headings:
                for heading in headings[:STRUCTURE_OUTLINE_MAX_ENTRIES]:
                    indent = "  " * heading.level
                    outline_lines.append(f"{indent}- Page {heading.page_num}: {heading.title}")
                omitted = len(headings) - STRUCTURE_OUTLINE_MAX_ENTRIES
                if omitted > 0:
                    outline_lines.append(f"  … ({omitted} more headings omitted)")
            else:
                outline_lines.append("  (No structural headings detected in PDF)")

            return "\n".join(outline_lines)
        except Exception as e:
            logger.warning("PDF structure outline extraction failed for %s: %s", path, e)
            return f"[PDF file: {path}] (Failed to extract structure outline: {e})"
        finally:
            import contextlib

            with contextlib.suppress(OSError):
                os.unlink(tmp_path)

    try:
        from myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor import (
            PDFExtractConfig,
            extract_pdf_content,
        )

        tmp_path = await _write_to_temp(raw_bytes)
        try:
            result = await extract_pdf_content(tmp_path, PDFExtractConfig(max_pages=PDF_READ_PAGE_WINDOW))
        finally:
            os.unlink(tmp_path)

    except (ImportError, TypeError):
        logger.warning("pdf_content_extractor not available for: %s", path)
        return f"[PDF file: {path}] (PDF extraction module not available)"
    except Exception as e:
        logger.warning("PDF extraction failed for %s: %s", path, e)
        return f"[PDF file: {path}] (Extraction failed)"

    text = result.text
    if not text.strip() and not result.images:
        return f"[PDF file: {path}] (No extractable content — may be encrypted)"

    text, pages_read = _cap_text(text, min(result.parsed_pages, PDF_READ_PAGE_WINDOW))
    partial_read_hint = _build_partial_read_hint(result.page_count, pages_read)
    coverage_note = _build_coverage_note(result)

    body = f"[PDF: {path}]\n{coverage_note}{text}{partial_read_hint}" if text.strip() or coverage_note else ""
    lead: list[ContentBlock] = [create_text_block(body)] if body else []

    if supports_vision and result.images:
        return [*lead, *(create_image_block(base64=img.data, mime_type=img.mime_type) for img in result.images)]

    if result.images and (vision_fallback_model_cfg is not None or vision_fallback_model_cfgs is not None):
        described = await _describe_pdf_pages(
            executor, result, path, vision_fallback_model_cfg, vision_fallback_model_cfgs
        )
        if described:
            return [*lead, create_text_block(described)]

    if body:
        return body

    return f"[PDF file: {path}] (No extractable text — may be image-only)"


def _format_page_ranges(pages: list[int]) -> str:
    """Compact ``1-3, 7`` form for a page list, so the note stays cheap in context.

    Sorts and de-duplicates rather than trusting the caller: page numbers arrive from set
    arithmetic and from the extractor, and an unsorted list would render as ``5, 1``.
    """
    ordered = sorted(set(pages))
    if not ordered:
        return ""
    ranges: list[str] = []
    start = prev = ordered[0]
    for page in ordered[1:]:
        if page == prev + 1:
            prev = page
            continue
        ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
        start = prev = page
    ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
    return ", ".join(ranges)


def _cap_text(text: str, pages_read: int) -> tuple[str, int]:
    """Cut ``text`` at the character cap and return it with the pages the model still holds.

    The extractor counts the pages of its window before this cap applies, so once the cap
    cuts, the pages read are those the kept text still reaches. The page the cut runs through
    counts, and the truncation line shows where it stopped. A text without page markers has
    nothing to count and keeps the extractor's figure.
    """
    if len(text) <= _FALLBACK_MAX_CHARS:
        return text, pages_read
    from myrm_agent_harness.toolkits.file_parsers.pdf.pdf import pages_with_text

    kept = text[:_FALLBACK_MAX_CHARS]
    reached = max(pages_with_text(kept), default=pages_read)
    return f"{kept}\n\n... [truncated at {_FALLBACK_MAX_CHARS} chars]", min(pages_read, reached)


def _build_partial_read_hint(page_count: int, pages_read: int) -> str:
    """Suffix for a document longer than the read window, or ``""``.

    Without it the model treats the delivered pages as the whole document and answers
    questions about the rest from nothing. It promises no way to read on, because
    file_read has none; the structure outline is the one way to learn what the rest holds.
    """
    if page_count <= PDF_READ_PAGE_WINDOW:
        return ""
    return (
        f"\n\n[Partial Read] This document has {page_count} pages; "
        f"only the first {pages_read} pages were read "
        "and file_read cannot open the rest. "
        "Do not assume what the unread pages contain; "
        "`parse_mode='structure'` lists the headings with their page numbers."
    )


def _build_coverage_note(result: PDFExtractResult) -> str:
    """Prefix that states which pages the delivered text cannot cover, or ``""``.

    The text layer returns nothing for a scanned page, so without this the model would
    read a partial document and answer as if it had seen all of it. Rendered next to the
    page count it tells the model which pages to treat as unread, and that a vision route
    is what could read them.
    """
    missing = result.pages_without_text
    if not missing:
        return ""

    shown = missing if len(missing) <= 12 else missing[:12]
    listing = _format_page_ranges(shown)
    if len(missing) > len(shown):
        listing += f", … ({len(missing)} pages total)"
    # Count against what was delivered, not the whole document: on a windowed read the
    # denominators differ, and quoting the total would imply the unread pages are a small
    # share of material the model never received either way.
    delivered = result.parsed_pages or result.page_count

    # Only promise the page images that this delivery actually carries. Past the image
    # ceiling some of these pages have no image either, and their content is simply absent.
    carried = {img.page_number for img in result.images if img.page_number > 0}
    with_image = [page for page in missing if page in carried]
    without_image = [page for page in missing if page not in carried]
    if without_image and len(without_image) < len(missing):
        availability = (
            f"Content of pages {_format_page_ranges(with_image)} is only available as page images; "
            f"pages {_format_page_ranges(without_image)} were not delivered at all."
        )
    elif without_image:
        availability = "Those pages were not delivered, so their content is unavailable."
    else:
        availability = "Their content is only available as page images."

    if len(missing) >= delivered:
        # Nothing readable in the delivered window, so "the text below omits them" would
        # describe text that is not there. Say what is actually true instead.
        return (
            f"[PDF coverage] none of the {delivered} delivered pages have a text layer "
            f"(scanned images or blank pages). {availability}\n\n"
        )
    return (
        f"[PDF coverage] {len(missing)} of the {delivered} delivered pages have no text layer "
        f"(scanned images or blank pages): pages {listing}. "
        f"The text below omits those pages; {availability}\n\n"
    )


async def _describe_pdf_pages(
    executor: CodeExecutor,
    result: PDFExtractResult,
    path: str,
    vision_fallback_model_cfg: object | None,
    vision_fallback_model_cfgs: object | None,
) -> str:
    """Describe delivered page images via the auxiliary vision chain.

    Mirrors the sibling image/video readers: the page images were already rendered for
    this delivery, so converting them here keeps a text-only model from losing every
    scanned page. Returns ``""`` when the chain is unconfigured or every page fails, so
    the caller falls back to plain text instead of crashing the read.
    """
    from myrm_agent_harness.toolkits.llms.vision.fallback_engine import (
        create_vision_fallback_engine,
    )

    engine = create_vision_fallback_engine(vision_fallback_model_cfg, vision_fallback_model_cfgs)
    if engine is None:
        return ""

    descriptions: list[str] = []
    for index, img in enumerate(result.images, start=1):
        try:
            page_text = await engine.describe_image_b64(img.data, img.mime_type)
        except Exception as exc:
            logger.warning("Vision fallback failed for PDF %s page %d: %s", path, index, exc)
            continue
        if page_text.strip():
            # Prefer the real source page so the model can cite the document correctly.
            label = img.page_number if img.page_number > 0 else index
            descriptions.append(f"[Page {label}]\n{page_text}")

    if not descriptions:
        return ""
    return f"[PDF page analysis for {path}]\n" + "\n\n".join(descriptions)
