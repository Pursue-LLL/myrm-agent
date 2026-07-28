---
name: office-document
description: >-
  Professional document generation and editing workflow for Excel (.xlsx), PowerPoint (.pptx),
  and Word (.docx). Creates new documents and safely edits existing files — preserving
  formulas, formatting, and structure. Uses openpyxl, python-pptx, and python-docx.
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
    - "Phase 5: Visual Preview — render to PDF via soffice then rasterize to PNG via pdftoppm, inspect for layout issues, self-correct up to 3 rounds (cloud sandbox only; skipped if soffice unavailable)"
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
    - step_id: visual_quality
      description: "Visual rendering check — no text overflow, element overlap, or contrast issues"
      validation_method: "Convert to PDF via soffice headless, rasterize to PNG via pdftoppm, inspect screenshots for layout defects"
      is_required: false
  success_criteria: "Professional document that is immediately usable without manual formatting fixes"
  estimated_duration_seconds: 900
---

# Office Document Generation

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## Harness audit contract

The harness runs an automatic Office write-fidelity audit after every successful `bash_code_execute_tool` call.

1. **Include file paths in the bash command text** — e.g. `python edit.py /workspace/report.xlsx`, not only `python edit.py`. Paths mentioned in the command get a pre-execution baseline for formula and formatting checks.
2. **Read `Office:` warnings in tool output** — they appear after bash stdout when fidelity checks fail:
   - formula removed or overwritten
   - DOCX formatting degradation (run-property drop)
   - Excel `#REF!` / `#NAME?` errors after LibreOffice recalc (when `soffice` is available)
   - baseline missing when the path was not in the command
3. **Formula diff vs recalc** — the harness compares formula sets before/after edits, then optionally recalculates workbooks that still contain formulas to catch broken references the diff cannot see.
4. **Self-correct** — when an `Office:` warning appears, fix the script and re-run; do not tell the user the file is ready.

## Overview

Business documents must be immediately usable — not "almost done, just needs formatting." This workflow ensures every generated document meets professional standards: correct formulas in Excel, clean layouts in PowerPoint, proper styling in Word.

## Phase 0: Create vs. Modify Detection

Before starting, determine if the task involves **creating a new document** or **modifying an existing one**:

- **Create**: user asks to "make", "generate", "create", "write" a document → proceed to Phase 1.
- **Modify**: user asks to "change", "update", "fix", "edit", "replace" content in an existing file → use the incremental edit workflow below.

### Incremental Edit Workflow

When modifying an existing Office document:

1. **Read structure** — call `file_read_tool(paths=["<file>"], parse_mode="structure")` to get the JSON structural map (shape IDs, paragraph IDs, table locations, styles).
2. **Locate target** — identify the exact element to modify by its stable ID (`shape_id` for PPTX, `para_id` for DOCX, cell coordinate for XLSX).
3. **Write targeted patch** — use `bash_code_execute_tool` with python-pptx/python-docx/openpyxl to open the file and modify only the targeted element(s). Reference elements by their stable IDs.
4. **Validate** — re-read the file to confirm the change took effect and no other content was damaged.

**Why this matters:** Rewriting the entire file from scratch to change one slide title wastes tokens, risks losing formatting, and breaks any content the user did not ask to change. The structure map enables surgical edits.

### Template Form Fill Mode (Word)

When modifying an existing `.docx` to **fill in data** (form fields, placeholders, table cells), use XML-level manipulation to preserve the original formatting. The standard `paragraph.text = "xxx"` assignment **destroys all formatting** (fonts, sizes, colors, bold/italic) — never use it for form filling.

#### Detection

Activate this mode when **all** conditions are met:

1. An existing `.docx` file is provided (Phase 0 → Modify)
2. The intent is to fill in data (keywords: 填写, fill, 填表, populate, template)
3. The document has structured placeholders (e.g., `___`, `XXX`, `【】`, table cells to fill)

#### XML-Level Write Technique

Replace placeholder text at the `<w:t>` element level while preserving the `<w:rPr>` (run properties) and `<w:pPr>` (paragraph properties):

```python
from docx import Document
from docx.oxml.ns import qn

doc = Document("template.docx")

for para in doc.paragraphs:
    for run in para.runs:
        if "___" in run.text or "XXX" in run.text:
            t_elem = run._element.find(qn("w:t"))
            if t_elem is not None:
                t_elem.text = t_elem.text.replace("___", actual_value)
                t_elem.set(qn("xml:space"), "preserve")
```

For table cell filling, iterate cells and apply the same technique:

```python
for table in doc.tables:
    for row in table.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                for run in para.runs:
                    t_elem = run._element.find(qn("w:t"))
                    if t_elem is not None and is_placeholder(t_elem.text):
                        t_elem.text = replacement_value
                        t_elem.set(qn("xml:space"), "preserve")
```

For **empty cells** (no existing runs), create a new run and copy formatting from a neighboring cell to maintain visual consistency:

```python
from copy import deepcopy

for table in doc.tables:
    for row in table.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                if not para.runs and cell_needs_filling(cell):
                    new_run = para.add_run(fill_value)
                    donor = find_donor_run(row)
                    if donor is not None:
                        new_run._element.insert(0, deepcopy(donor._element.find(qn("w:rPr"))))

def find_donor_run(row):
    """Find the first run with formatting in the same row."""
    for c in row.cells:
        for p in c.paragraphs:
            for r in p.runs:
                if r._element.find(qn("w:rPr")) is not None:
                    return r
    return None
```

#### Placeholder Cleanup Rules

After filling, clean up residual placeholder artifacts:

- Remove unfilled placeholder markers (`___`, `XXX`, `【待填写】`) — replace with empty string
- Remove instruction text (e.g., `（此处填写公司名称）`) from the final output
- Preserve intentional blanks in unfilled optional fields — leave as empty string, do not delete the paragraph

#### Multi-File Form Fill Workflow

When multiple documents need to be filled from the same data source:

1. Parse all template files first to build a unified field map
2. Resolve data mappings once (user data → placeholder names)
3. Fill each file sequentially, reusing the same replacement map
4. Validate all files in a single Phase 5 batch

#### Forbidden in Form Fill Mode

- `paragraph.text = "new text"` — destroys all run-level formatting
- `cell.text = "new text"` — same issue for table cells
- `paragraph.clear()` then `paragraph.add_run()` — loses original font/size/color settings
- Deleting or reordering paragraphs — may break document structure
- `doc.save()` to the same path without backup — always write to a new output path

---

## Phase 1: Requirements

Before writing any code, clarify:

1. **Document type** — Excel, PowerPoint, or Word?
2. **Content** — What data or text goes into the document?
3. **Structure** — How many sheets/slides/sections? What layout?
4. **Styling** — Corporate colors? Logo? Specific fonts?
5. **Output path** — Where to save the file?
6. **Scenario detection** — Check if the request matches a specialized scenario:
   - **Chinese official documents (公文):** keywords like 通知, 请示, 函, 批复, 纪要, 报告, 决定, 意见, 命令 → apply GB/T 9704 formatting
   - **Academic papers (学术论文):** keywords like 论文, 毕业论文, 学位论文, 课程论文 → apply academic formatting

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

#### Editing Existing Excel Files

When the user provides an existing `.xlsx` file to modify (fill data, update values), follow these rules **instead of** the "from scratch" conventions above. The existing file's conventions always take precedence.

##### Step 1: Identify formula cells vs input cells

Before writing any data, scan the workbook to understand its structure:

```python
from openpyxl import load_workbook

wb = load_workbook('template.xlsx')

formula_cells = set()
for ws in wb.worksheets:
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith('='):
                formula_cells.add(f"{ws.title}!{cell.coordinate}")
```

If the file uses color conventions (blue for inputs, black for formulas), respect them.
If no color marks exist, treat any cell whose value starts with `=` as a formula cell — do not touch it.

##### Step 2: Write only to input cells

```python
# CORRECT — write to a non-formula cell
ws['B2'] = 5000000

# WRONG — overwrites a SUM formula with a hardcoded number
ws['B10'] = 10000000  # B10 was =SUM(B2:B9)
```

##### Step 3: Verify formula integrity after writing

After all edits, audit the file to confirm no formulas were lost:

```python
post_edit_formulas = set()
for ws in wb.worksheets:
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith('='):
                post_edit_formulas.add(f"{ws.title}!{cell.coordinate}")

lost = formula_cells - post_edit_formulas
if lost:
    raise RuntimeError(f"Formulas lost in cells: {lost}")

wb.save('output.xlsx')
```

If formulas were lost, do **not** deliver the file. Investigate, fix, and retry.

##### Forbidden operations on existing files

- **Never** assign a plain value to a cell that contains a formula (`=` prefix)
- **Never** use `insert_rows()` / `delete_rows()` / `insert_cols()` / `delete_cols()` within a range referenced by formulas — this silently shifts formula references
- **Never** use `pandas.to_excel()` to overwrite a file that contains formulas — pandas destroys all formulas
- **Never** call `wb.save()` after loading with `data_only=True` — this permanently replaces every formula with its last cached value

##### openpyxl pitfalls for existing files

| Pitfall | Consequence | Prevention |
|---------|-------------|------------|
| `load_workbook(data_only=True)` then `save()` | All formulas permanently replaced by cached values | Never save a `data_only=True` workbook |
| Re-saving a file with external workbook links (`[1]Sheet!A1`) | Links lost, cells become `#NAME?` after recalc | Copy cached values from original before editing |
| Writing to a `MergedCell` (non-anchor) | `AttributeError` or silent data loss | Only write to the top-left anchor of merged ranges |
| Opening `.xlsm` without `keep_vba=True` | All macros stripped on save | Always pass `keep_vba=True` for macro-enabled files |

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

#### Native Objects Discipline

Charts and tables in PPTX MUST be native PowerPoint objects — never screenshots or text-box imitations:

```python
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches

chart_data = CategoryChartData()
chart_data.categories = ['Q1', 'Q2', 'Q3', 'Q4']
chart_data.add_series('Revenue', (120, 135, 148, 162))

chart_frame = slide.shapes.add_chart(
    XL_CHART_TYPE.COLUMN_CLUSTERED,
    Inches(1), Inches(2), Inches(8), Inches(4.5),
    chart_data,
)
```

Tables MUST use `slide.shapes.add_table()`, never TextBox arrangements:

```python
rows, cols = 4, 3
table_shape = slide.shapes.add_table(rows, cols, Inches(1), Inches(2), Inches(8), Inches(3))
table = table_shape.table
table.cell(0, 0).text = "Metric"
table.cell(0, 1).text = "Target"
table.cell(0, 2).text = "Actual"
```

**Forbidden anti-patterns:**
- Embedding matplotlib/PIL screenshots as chart images (not editable)
- Arranging TextBoxes to simulate table layout (cannot add/remove rows)
- Using placeholder images instead of actual data-bound charts

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

#### Chinese Official Documents (公文/政务文档)

When the user's request involves official government documents — keywords: 公文, 通知, 请示, 函, 批复, 纪要, 报告, 决定, 意见, 命令 — apply these formatting rules **instead of** the default Calibri/11pt standards:

| Element | Font | Size | Notes |
|---------|------|------|-------|
| Title (标题) | 小标宋体 | 22pt (二号) | Centered, bold |
| Body (正文) | 仿宋_GB2312 | 16pt (三号) | Justified |
| Document number (发文字号) | 仿宋_GB2312 | 16pt (三号) | Centered |
| Headings (一级标题) | 黑体 | 16pt (三号) | — |
| Subheadings (二级标题) | 楷体_GB2312 | 16pt (三号) | — |

**Font fallback chain:** 仿宋_GB2312 → FangSong → SimSun (system resolves at open time)

**Layout (GB/T 9704-2012):**
- Line spacing: 28pt fixed (固定值 28 磅)
- Page margins: top 3.7cm, bottom 3.5cm, left 2.8cm, right 2.6cm
- Page size: A4

**Structure template:**

```
[发文机关标志 — 红色、居中、二号小标宋]
————————————————————（红色分隔线）
[发文字号]                              [签发人（上行文）]
[标题 — 二号小标宋、居中]
[主送机关：]
[正文 — 三号仿宋、28磅固定行距]
[署名（发文机关）]                    [成文日期]
```

```python
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

doc = Document()

# Page setup (GB/T 9704-2012)
section = doc.sections[0]
section.top_margin = Cm(3.7)
section.bottom_margin = Cm(3.5)
section.left_margin = Cm(2.8)
section.right_margin = Cm(2.6)

# Normal style — FangSong_GB2312, 16pt, 28pt fixed line spacing
style = doc.styles['Normal']
style.font.name = '仿宋_GB2312'
style.font.size = Pt(16)
style.element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋_GB2312')
style.paragraph_format.line_spacing = Pt(28)
style.paragraph_format.line_spacing_rule = 4  # EXACTLY

# Title
title_para = doc.add_paragraph()
title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = title_para.add_run('关于XX的通知')
run.font.name = '小标宋体'
run.element.rPr.rFonts.set(qn('w:eastAsia'), '小标宋体')
run.font.size = Pt(22)
run.font.bold = True
```

**Forbidden in official documents:**
- Calibri, Arial, Times New Roman, or any Latin-only font for body text
- Single/1.5x/double line spacing (must be 28pt fixed)
- 1-inch margins (must follow GB/T 9704)

---

#### Academic Papers (学术论文)

When the user's request involves academic papers — keywords: 论文, 毕业论文, 学术报告, 学位论文, 课程论文 — apply these formatting rules:

| Element | Font | Size | Notes |
|---------|------|------|-------|
| Title | 黑体 | 16pt (小二号) | Centered, bold |
| Body | 宋体 / Times New Roman | 12pt (小四号) | Justified |
| Headings (一级) | 黑体 | 14pt (四号) | Bold |
| Headings (二级) | 黑体 | 12pt (小四号) | Bold |
| Abstract label | 黑体 | 12pt | Centered |
| Abstract content | 楷体 | 12pt | — |

**Layout:**
- Line spacing: 1.5x (多倍行距 1.5)
- Page margins: top 2.54cm, bottom 2.54cm, left 3.17cm, right 3.17cm
- Page size: A4

**Structure:**
1. Title (标题)
2. Author & affiliation (作者、单位)
3. Abstract (摘要) + Keywords (关键词)
4. Body sections (正文各章节)
5. References (参考文献)
6. Acknowledgments (致谢)

```python
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn

doc = Document()

section = doc.sections[0]
section.top_margin = Cm(2.54)
section.bottom_margin = Cm(2.54)
section.left_margin = Cm(3.17)
section.right_margin = Cm(3.17)

style = doc.styles['Normal']
style.font.name = 'Times New Roman'
style.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
style.font.size = Pt(12)
style.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
```

---

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

## Phase 5: Visual Preview & Self-Correction

After Phase 4 passes, render the document to PNG and visually inspect the output.
This phase only runs when `soffice` is available (cloud sandbox). If unavailable, skip and deliver the Phase 4 result.

### Step 1: Environment check

```bash
which soffice
```

If the command fails, **skip Phase 5 entirely** — the document is still valid from Phase 4.

### Step 2: Render to PNG

Convert via PDF first (soffice direct PNG export only captures the first page/slide), then rasterize with `pdftoppm` (poppler-utils):

```bash
mkdir -p /tmp/office_preview
soffice --headless --convert-to pdf --outdir /tmp/office_preview ./output/report.pptx
pdftoppm -png -r 200 /tmp/office_preview/report.pdf /tmp/office_preview/page
```

This produces `page-01.png`, `page-02.png`, etc. — one PNG per slide/page. Works identically for DOCX, PPTX, and XLSX.

### Step 3: Visual inspection

Examine each rendered PNG for these defects:

| Defect | What to look for |
|--------|------------------|
| **Text overflow** | Text cut off at shape/cell boundaries |
| **Element overlap** | Shapes, charts, or text boxes obscuring each other |
| **Low contrast** | Light text on light background or dark on dark |
| **Excessive whitespace** | Large empty areas that waste slide/page real estate |
| **Chart/table truncation** | Data labels, axis labels, or table rows cut off |
| **Font substitution** | Filled text visually differs from template text (wrong font family, weight, or size) — indicates formatting was lost during write |
| **Line spacing overflow** | Filled content pushes lines beyond the cell/frame boundary — reduce font size or truncate |
| **Residual placeholders** | Unfilled `___`, `XXX`, or `【】` markers still visible in the rendered output |

### Step 4: Self-correct (max 3 rounds)

If defects are found:

1. Identify the root cause in the generation code (e.g., font size too large, shape position overlapping)
2. Fix the generation code
3. Re-generate the document
4. Re-render and re-inspect

After 3 rounds, deliver the best result regardless.

### Step 5: Deliver

Deliver the final document file and attach the preview PNG(s) so the user can see the visual result directly in chat.
