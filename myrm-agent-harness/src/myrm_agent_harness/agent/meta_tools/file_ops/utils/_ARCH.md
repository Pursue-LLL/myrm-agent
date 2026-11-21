# utils/

## Overview
Utility functions module.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Utility functions module. | — |
| document_reader.py | Core | Document file reader for file_read_tool. Converts .docx/.doc/.xlsx/.xls/.pptx/.ppt/.ipynb to Markdown via file_parsers with multimodal plot blocks and magic bytes sniffing. A workbook read as its structure (asked for, or a large one by default) shows no cell values, so its result ends with the call that reads them (`parse_mode='content'`). | ✅ |
| file_utils.py | Core | `parse_path_with_range`: the file and the validated line range (positive numbers in order) of a path argument. It reads the range with `READ_RANGE_PATTERN` of `core.security.tool_registry`, the grammar the permission verdict strips ranges with (`strip_read_range`), so the file read is the file judged. Only a trailing `:START-END` or `:START-` is a range; every other colon, such as a drive letter or the one in `notes:v2.md`, belongs to the file name. The file name comes back as written: no spelling of a path (a short file id, for one) is swapped for another file after the verdict. | ✅ |
| image_reader.py | Core | Provides is_image_path, read_image_as_content_blocks. Quality Ladder compression (95->20) + (original/attached/scale) coordinate scale factor disclosure. | ✅ |
| line_endings.py | Core | Line ending detection and normalization (CRLF/LF preserved across edits), UTF-8 BOM stripping on display, and `view_lines`, the lines a view shows for text split on LF (CRLF and a bare CR end a line too). | ✅ |
| vault_scope.py | Core | Obsidian vault root detection via `.obsidian/` marker | ✅ |
| office_scope.py | Core | Office `.docx`/`.xlsx` extension scope for write guards | ✅ |
| office_opc.py | Core | OPC metrics + xlsx formula snapshots + corrupt Office file audit read errors for bash post-audit | ✅ |
| office_recalc.py | Core | Optional LibreOffice recalc + Excel error cell scan after xlsx edits | ✅ |
| video_reader.py | Core | Sandbox video reads for file_read_tool; video-slot-first fallback chain + VideoAnalysisEngine. | ✅ |
| vault_read.py | Core | vault:// URI read, workspace resolve, batch read for file_read_tool. Lines are numbered by newline only (as every other read path does, not `str.splitlines`); the continuation hint of a truncated read names the object (`vault://<id>`, never the range just read) and counts from the first line read. | ✅ |
| pdf_reader.py | Core | PDF file reader with structure outline extraction (`parse_mode='structure'`; headings past `STRUCTURE_OUTLINE_MAX_ENTRIES` are only counted). A read delivers the first `PDF_READ_PAGE_WINDOW` pages; a longer document ends with one `[Partial Read]` hint that states how many pages were read (when the character cap cuts the text short, the pages the kept text still reaches), says `file_read` cannot open the rest and points to the outline. Reading never ingests anything into a knowledge base. Delivery mirrors the sibling readers: a vision model gets page image blocks, a text-only model with an auxiliary vision chain gets the same pages as text descriptions (real source page numbers from `PDFImageContent.page_number`), and a text layer that could not read some pages is disclosed through a `[PDF coverage]` prefix. | ✅ |

## Tests

- `tests/agent/meta_tools/file_ops/utils/test_office_opc.py`
- `tests/agent/meta_tools/file_ops/utils/test_office_recalc.py`

## Key Dependencies

- `toolkits`
- `core.security.tool_registry` (the line-range grammar `file_utils.py` parses with)
