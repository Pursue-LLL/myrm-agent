# file_read/

## Overview
How `file_read_tool` reads and shows a file: multimodal blocks, text pages, complete-line truncation and structural outlines. `file_read_tool.py` is the tool facade; `core/__init__` re-exports the handlers.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Facade over the handlers, truncation and outline modules below. | — |
| multimodal.py | Internal | Multimodal/vault execution handlers. Image reads route by capability: native vision blocks, else the auxiliary vision chain, else the OCR tier (`_read_image_via_ocr`), else a metadata line. PDFs go through `read_pdf_as_content_blocks` with the same vision-chain config so scanned pages survive on a text-only model. Plain text paths and structure outlines are delegated to `text_paths.py`. | ✅ |
| text_paths.py | Internal | Text read execution: preview/stream/all modes (>100MB falls back to preview), `read_structure_outline`, and the page cap. A file the context guard parked is paged by `parked_page_chars` and always read as `all` (preview and stream bypass the page cap). | ✅ |
| truncation.py | Internal | Output truncation helpers. Complete-line-boundary head truncation with precomputed next_offset and line-count cap. A gutter carries absolute line numbers; a raw slice (a ranged vault read) counts from `first_line`, so the continuation offset is always an absolute line. | ✅ |
| outline.py | Internal | Adaptive structural outline extractor (Markdown headings, code symbols, classes/functions with line ranges) for truncated reads and structure mode. | ✅ |

## Key Dependencies

- `core` (file operation service, operation context, result formatter, parked file view)
- `streaming`, `utils` (readers, vault read)
- `agent.security.redact`
