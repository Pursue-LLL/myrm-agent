---
name: document-extraction
description: >-
  Extract and transform content from documents (PDF, HTML, Markdown) into structured
  formats. Handles multi-page documents, tables, and complex layouts.
version: 1.0.0
category: data-collection
tags:
  - document
  - extraction
  - parsing
  - pdf
  - transformation
allowed-tools: file_read_tool web_fetch_tool bash_code_execute_tool file_write_tool
contract:
  steps:
    - "Phase 1: Ingest — load the document and assess its format and structure"
    - "Phase 2: Structure Analysis — identify sections, tables, headers, key-value pairs"
    - "Phase 3: Extract — pull out structured data using appropriate parsing methods"
    - "Phase 4: Transform — normalize and structure the extracted data"
    - "Phase 5: Output — save in the target format with metadata"
  potential_traps:
    - description: "Losing document structure during extraction (tables flattened, sections merged)"
      mitigation: "Preserve hierarchy; extract tables as separate structured objects"
      severity: medium
    - description: "Encoding issues causing garbled text in non-English documents"
      mitigation: "Detect encoding early; use utf-8 with fallback detection"
      severity: medium
  verification_steps:
    - step_id: content_complete
      description: "All sections of the source document are represented in the output"
      validation_method: "Compare section count and key headings between source and output"
      is_required: true
    - step_id: tables_preserved
      description: "Tables retain their row/column structure"
      validation_method: "Spot-check extracted tables against source for data accuracy"
      is_required: true
  success_criteria: "Complete, accurately structured extraction preserving document hierarchy"
  estimated_duration_seconds: 900
---

# Document Extraction

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## Overview

Documents contain structured information trapped in unstructured formats. This workflow extracts that structure systematically, preserving hierarchy, tables, and relationships.

## Phase 1: Ingest

1. **Load the document** — Use `file_read_tool` for local files, `web_fetch_tool` for URLs
2. **Identify the format** — PDF, HTML, Markdown, plain text, DOCX
3. **Assess complexity** — Simple text? Tables? Multi-column layout? Images with text?

### Format-Specific Loading

| Format | Tool | Notes |
|--------|------|-------|
| PDF | `bash_code_execute_tool` with Python (pdfplumber/pymupdf) | Best for tables and layout |
| HTML | `web_fetch_tool` or `file_read_tool` | Parse with BeautifulSoup |
| Markdown | `file_read_tool` | Already semi-structured |
| Plain text | `file_read_tool` | Requires pattern detection |

## Phase 2: Structure Analysis

Before extracting, understand the document structure:

1. **Identify sections** — Headers, chapters, numbered sections
2. **Find tables** — Rows, columns, merged cells
3. **Detect key-value pairs** — Labels followed by values (forms, specs)
4. **Note hierarchies** — Nested lists, subsections, parent-child relationships
5. **Flag special content** — Code blocks, formulas, footnotes, references

## Phase 3: Extract

### Text Content

```python
# For each section:
# 1. Identify the header level and title
# 2. Extract the body text
# 3. Preserve paragraph breaks
# 4. Maintain list structure (ordered/unordered)
```

### Tables

Tables require special handling to preserve structure:

```python
# Extract as list of dictionaries (rows with column headers as keys)
# Example output:
[
    {"Name": "Alice", "Role": "Engineer", "Team": "Backend"},
    {"Name": "Bob", "Role": "Designer", "Team": "Frontend"}
]
```

### Key-Value Pairs

Common in forms, spec sheets, and configuration documents:

```python
# Extract as dictionary
{
    "Document ID": "DOC-2024-001",
    "Status": "Approved",
    "Effective Date": "2024-01-15"
}
```

## Phase 4: Transform

Normalize the extracted data:

1. **Standardize dates** — Convert all date formats to ISO 8601
2. **Clean whitespace** — Remove extra spaces, normalize line breaks
3. **Resolve references** — Link footnotes, cross-references
4. **Deduplicate** — Remove repeated headers/footers from multi-page documents
5. **Type conversion** — Parse numbers, booleans, dates from strings

## Phase 5: Output

Save in the target format:

### JSON (Default)

```json
{
  "metadata": {
    "source": "document.pdf",
    "pages": 12,
    "extracted_at": "2024-01-15T10:30:00Z"
  },
  "sections": [...],
  "tables": [...],
  "key_value_pairs": {...}
}
```

### Markdown

Preserves readability while maintaining structure. Good for documentation pipelines.

### CSV

For tabular data only. Flatten nested structures into rows.

## Handling Edge Cases

| Issue | Strategy |
|-------|----------|
| Scanned PDF (image-based) | OCR with pytesseract or suggest user provides text version |
| Multi-column layout | Process columns separately, then merge |
| Mixed languages | Detect language per section; maintain encoding |
| Encrypted/protected documents | Report to user; cannot extract without permission |
