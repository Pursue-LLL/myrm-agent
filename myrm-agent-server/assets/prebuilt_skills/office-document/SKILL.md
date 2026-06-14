---
name: office-document
description: >-
  Professional document generation workflow for Excel (.xlsx), PowerPoint (.pptx),
  and Word (.docx). Produces business-grade documents with proper formatting,
  formulas, charts, and consistent styling using openpyxl, python-pptx, and python-docx.
version: 1.0.0
category: productivity
tags:
  - excel
  - powerpoint
  - word
  - document
  - report
  - spreadsheet
  - presentation
allowed-tools: bash_code_execute_tool file_write_tool file_read_tool
contract:
  steps:
    - "Phase 1: Requirements — clarify document type, content, structure, and styling preferences"
    - "Phase 2: Environment — ensure required Python packages are installed"
    - "Phase 3: Generate — create the document following format-specific conventions"
    - "Phase 4: Validate — verify the output file opens correctly and content is complete"
  potential_traps:
    - description: "Hardcoding computed values in Excel instead of using formulas"
      mitigation: "Every derived cell MUST be an Excel formula; only raw inputs may be hardcoded values"
      severity: high
    - description: "Creating presentations with walls of text instead of visual layouts"
      mitigation: "Enforce 6-word headlines, bullet points max 6 per slide, use visuals over text"
      severity: medium
    - description: "Missing pip install leading to ModuleNotFoundError at runtime"
      mitigation: "Always run pip install in Phase 2 before any generation code"
      severity: medium
  verification_steps:
    - step_id: file_created
      description: "Output file exists and is non-empty"
      validation_method: "Check file exists with ls -la and file size > 0"
      is_required: true
    - step_id: content_complete
      description: "All requested content sections are present in the document"
      validation_method: "Read back key sheets/slides/sections and verify against requirements"
      is_required: true
  success_criteria: "Professional document that is immediately usable without manual formatting fixes"
  estimated_duration_seconds: 900
---

# Office Document Generation

## Overview

Business documents must be immediately usable — not "almost done, just needs formatting." This workflow ensures every generated document meets professional standards: correct formulas in Excel, clean layouts in PowerPoint, proper styling in Word.

## Phase 1: Requirements

Before writing any code, clarify:

1. **Document type** — Excel, PowerPoint, or Word?
2. **Content** — What data or text goes into the document?
3. **Structure** — How many sheets/slides/sections? What layout?
4. **Styling** — Corporate colors? Logo? Specific fonts?
5. **Output path** — Where to save the file?

If not specified, use sensible defaults: professional blue theme, sans-serif fonts, clean layout.

## Phase 2: Environment

Install required packages before generation:

```bash
pip install openpyxl python-pptx python-docx
```

## Phase 3: Generate

### Excel (.xlsx) — openpyxl

#### Cell Color Convention

| Color | Meaning | Usage |
|-------|---------|-------|
| **Blue** (`Font(color="0000FF")`) | Input / assumption | Values the user may change |
| **Black** (default) | Formula / calculation | Derived cells — always use Excel formulas |
| **Green** (`Font(color="006100")`) | Cross-reference | Links to other sheets or external data |

#### Formulas Over Hardcodes

Every calculation MUST use Excel formula strings, not Python-computed values:

```python
# CORRECT — formula flexes when inputs change
ws["D10"] = "=B10*C10"
ws["D15"] = "=SUM(D10:D14)"

# WRONG — breaks when user edits inputs
ws["D10"] = price * quantity
```

Permitted hardcodes: raw data inputs, user assumptions, source data with cell comments.

#### Formatting Standards

```python
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill, numbers

header_font = Font(bold=True, size=11, color="FFFFFF")
header_fill = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
currency_format = '#,##0.00'
pct_format = '0.0%'
thin_border = Border(
    left=Side(style='thin'), right=Side(style='thin'),
    top=Side(style='thin'), bottom=Side(style='thin'),
)

for cell in ws[1]:
    cell.font = header_font
    cell.fill = header_fill
    cell.alignment = Alignment(horizontal='center')
```

#### Data Validation and Charts

```python
from openpyxl.chart import BarChart, Reference

chart = BarChart()
chart.title = "Revenue by Quarter"
chart.style = 10
data = Reference(ws, min_col=2, min_row=1, max_row=5, max_col=5)
cats = Reference(ws, min_col=1, min_row=2, max_row=5)
chart.add_data(data, titles_from_data=True)
chart.set_categories(cats)
ws.add_chart(chart, "G2")
```

#### Sheet Organization

- First sheet: Summary / Dashboard
- Data sheets: one logical dataset per sheet
- Last sheet: Assumptions / Notes (if applicable)
- Freeze panes on header row: `ws.freeze_panes = "A2"`
- Auto-filter on data tables: `ws.auto_filter.ref = ws.dimensions`
- Set column widths for readability

---

### PowerPoint (.pptx) — python-pptx

#### Slide Composition Rules

- **Title slide**: Title + subtitle + date
- **Content slides**: Headline (max 6 words) + bullet points (max 6 per slide) or visual
- **Data slides**: Chart or table with a clear takeaway headline
- **Closing slide**: Key takeaways or next steps

#### Layout Standards

```python
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RgbColor
from pptx.enum.text import PP_ALIGN

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)

slide = prs.slides.add_slide(prs.slide_layouts[1])
title = slide.shapes.title
title.text = "Q2 Revenue Summary"
title.text_frame.paragraphs[0].font.size = Pt(28)

body = slide.placeholders[1]
tf = body.text_frame
tf.text = "Revenue grew 15% QoQ driven by enterprise segment"
for para in tf.paragraphs:
    para.font.size = Pt(18)
```

#### Visual Guidelines

- Consistent color palette across all slides
- One key message per slide
- Charts over tables; tables over bullet lists
- Add slide numbers
- Sans-serif fonts (Calibri, Arial, or system default)

---

### Word (.docx) — python-docx

#### Document Structure

```python
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

doc = Document()

style = doc.styles['Normal']
style.font.name = 'Calibri'
style.font.size = Pt(11)
style.paragraph_format.space_after = Pt(6)

doc.add_heading('Quarterly Business Review', level=0)
doc.add_paragraph('Prepared by Analytics Team | Q2 2026')

doc.add_heading('Executive Summary', level=1)
doc.add_paragraph('Revenue grew 15% quarter-over-quarter...')
```

#### Formatting Standards

- Heading 1 for major sections, Heading 2 for subsections
- 11pt body text, 1.15 line spacing
- Page margins: 1 inch all sides
- Tables with header row formatting (bold, shaded)
- Page breaks between major sections
- Include table of contents for documents > 5 pages

#### Table Formatting

```python
table = doc.add_table(rows=4, cols=3, style='Light Grid Accent 1')
table.rows[0].cells[0].text = 'Metric'
table.rows[0].cells[1].text = 'Q1'
table.rows[0].cells[2].text = 'Q2'

for cell in table.rows[0].cells:
    cell.paragraphs[0].runs[0].font.bold = True
```

## Phase 4: Validate

After generating:

1. **File exists** — Check with `ls -la` and verify non-zero size
2. **Content check** — For Excel: read back key cells to verify formulas. For PPTX/DOCX: verify slide/section count
3. **Report to user** — Confirm file path and summary of contents

```python
import os
filepath = "./output/report.xlsx"
size = os.path.getsize(filepath)
print(f"Created: {filepath} ({size:,} bytes)")
```
