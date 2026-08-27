---
name: pdf-generator
description: >-
  Professional PDF document generation workflow for business invoices, financial audits,
  analytical reports, and structured documents. Compiles high-fidelity PDFs via ReportLab,
  WeasyPrint, or HTML+Chromium printing, featuring multi-round visual verification and CJK font support.
version: 1.0.0
category: productivity
tags:
  - pdf
  - invoice
  - report
  - document
  - generation
  - printing
allowed-tools: bash_code_execute_tool file_write_tool file_read_tool
contract:
  steps:
    - "Phase 1: Requirements & Layout — clarify document type, table structures, pagination boundaries, and color theme"
    - "Phase 2: Environment Check — ensure Python PDF libraries (reportlab, weasyprint, or chromium print pipeline) are ready"
    - "Phase 3: Code Generation — synthesize declarative document generation script with pagination guards and CJK fonts"
    - "Phase 4: Compilation — execute PDF generation script in sandbox and verify file creation"
    - "Phase 5: Visual Self-Correction — rasterize page 1 to PNG via pdftoppm, inspect for overflow/overlap, self-correct up to 3 rounds"
  potential_traps:
    - description: "Page break splitting table rows or headers awkwardly"
      mitigation: "Enforce CSS Paged Media 'page-break-inside: avoid' on table rows or use KeepTogether in ReportLab"
      severity: high
    - description: "CJK characters rendering as tofu boxes due to missing font registration"
      mitigation: "Always specify fallback sans-serif fonts (Noto Sans CJK, WenQuanYi, or system fallback)"
      severity: high
    - description: "Text overflowing fixed container boundaries in invoices or receipts"
      mitigation: "Use dynamic flowables or auto-wrapping table cells instead of hardcoded coordinates"
      severity: medium
  verification_steps:
    - step_id: pdf_file_created
      description: "Target PDF file exists and has size > 0"
      validation_method: "Check file exists with ls -la and non-zero byte size"
      is_required: true
    - step_id: visual_layout_quality
      description: "No text clipping, overlapping elements, or broken pagination"
      validation_method: "Convert to PNG via pdftoppm and inspect visual layout"
      is_required: true
  success_criteria: "Pixel-perfect, enterprise-grade PDF document immediately ready for download and distribution"
  estimated_duration_seconds: 600
---

# PDF Document Generation

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

Important safety rules:
- Execute each command independently (do NOT use semicolons `;` or inline subshells `$()`, which are blocked by security policy).
- To install required Python libraries (like `reportlab`), run `pip install reportlab` as a separate single command.
- To execute scripts, write them with `file_write_tool` first or run `python3 script.py` directly.

## Overview

Business documents (commercial invoices, tax receipts, project status reports, audit summaries) demand publication-quality PDF rendering. This workflow ensures that all generated PDFs have clean pagination, robust typography, proper table formatting, and zero rendering defects.

---

## Phase 1: Requirements & Document Design

Determine the target document format:
1. **Invoice / Receipt**: Compact 1-page layout, structured party headers (Seller/Buyer), itemized line tables, tax calculations, payment summary.
2. **Executive Report / Audit**: Multi-page layout, cover block, executive summary, KPI metric cards, data tables, SVG chart embeds, and signature seals.
3. **Technical Analysis / Documentation**: Multi-section layout with monospace code snippets, structured callouts, and numbered headings.

---

## Phase 2: Engine Selection & Script Synthesis

Depending on complexity, select the appropriate Python rendering stack:

### Approach A: HTML + CSS Paged Media (Recommended for modern, rich layouts)

Use `weasyprint` or Python headless Chromium print:

```python
# build_pdf.py
html_content = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
@page {
    size: A4;
    margin: 20mm 15mm 20mm 15mm;
    @bottom-right {
        content: counter(page) " / " counter(pages);
        font-size: 9pt;
        color: #718096;
    }
}
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", sans-serif;
    color: #1a202c;
    line-height: 1.5;
}
.page-break-avoid {
    page-break-inside: avoid;
    break-inside: avoid;
}
table {
    width: 100%;
    border-collapse: collapse;
}
th, td {
    padding: 8px 12px;
    border-bottom: 1px solid #e2e8f0;
}
th {
    background-color: #f7fafc;
    font-weight: 600;
}
</style>
</head>
<body>
    <!-- Document Content Here -->
</body>
</html>
"""

from weasyprint import HTML
HTML(string=html_content).write_pdf("output.pdf")
```

### Approach B: Direct ReportLab (Recommended for lightweight, standalone generation)

```python
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

doc = SimpleDocTemplate("output.pdf", pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
styles = getSampleStyleSheet()
story = []

# Build story items with Paragraph, Table, Spacer
# Enforce KeepTogether on important blocks
doc.build(story)
```

---

## Phase 3: Visual Inspection & Self-Correction

After generating the PDF in the sandbox:

1. **Rasterize page 1 to PNG**:
   ```bash
   pdftoppm -png -r 150 -f 1 -l 1 output.pdf preview_page1
   ```
2. **Inspect Preview**: Check for:
   - Text overlap or clipping
   - Table column squishing
   - Broken page splits
3. **Self-Correct**: If any visual flaws exist, adjust CSS padding, column widths, or font sizes and re-compile.

---

## Phase 4: Output Verification

- Verify the output PDF file exists: `ls -la output.pdf`
- Return clear download link and metadata to the user.
