# file_read/

## Overview
How `file_read_tool` reads and shows a file: multimodal blocks, text pages, complete-line truncation and structural outlines, and which paths it may read. `file_read_tool.py` is the tool facade; `core/__init__` re-exports the handlers, and only the tool uses the scope guards.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Facade over the handlers, truncation and outline modules below. | — |
| multimodal.py | Internal | Multimodal/vault execution handlers. Image reads route by capability: native vision blocks, else the auxiliary vision chain, else the OCR tier (`_read_image_via_ocr`), else a metadata line. PDFs go through `read_pdf_as_content_blocks` with the same vision-chain config so scanned pages survive on a text-only model. Plain text paths and structure outlines are delegated to `text_paths.py`. | ✅ |
| text_paths.py | Internal | Text read execution: preview/stream/all modes (>100MB falls back to preview), `read_structure_outline`, and the page cap. A file the context guard parked is paged by `parked_page_chars`, with the token budget `page_token_budget` derives from the window the run context reports, and always read as `all` (preview and stream bypass the page cap). | ✅ |
| truncation.py | Internal | Output truncation helpers. Complete-line-boundary head truncation with precomputed next_offset and line-count cap. A gutter carries absolute line numbers; a raw slice (a ranged vault read) counts from `first_line`, so the continuation offset is always an absolute line. | ✅ |
| scope.py | Internal | Read-scope guards the tool runs before any read. `assert_paths_allowed_for_read` blocks a path under a disabled skill root. `assert_evicted_uploaded_read_scope` confines the Fast track (`path_policy=evicted_uploaded`) to UECD spill, `_uploaded` and the spilled long-paste directories (`context_guard` constants): `path_hint_allowed_for_evicted_uploaded` is the lexical test (a `..` segment never passes it), and a path that fails it is judged by where the executor resolves it. `is_url` marks the network URLs the tool refuses. | ✅ |
| outline.py | Internal | Adaptive structural outline extractor (Markdown headings, code symbols, classes/functions with line ranges) for truncated reads and structure mode. | ✅ |

## Key Dependencies

- `core` (file operation service, operation context, result formatter, parked file view)
- `streaming`, `utils` (readers, vault read)
- `agent.security.redact`
- `agent.context_guard` (spilled long-text directory constants), `agent.meta_tools.file_search.skill_path_filter` (disabled skill roots)
