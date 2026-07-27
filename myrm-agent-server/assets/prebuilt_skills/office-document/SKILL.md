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

## Overview

Business documents must be immediately usable — not "almost done, just needs formatting." This workflow ensures every generated document meets professional standards: correct formulas in Excel, clean layouts in PowerPoint, proper styling in Word.

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

Examine each rendered PNG for these 5 defects:

| Defect | What to look for |
|--------|------------------|
| **Text overflow** | Text cut off at shape/cell boundaries |
| **Element overlap** | Shapes, charts, or text boxes obscuring each other |
| **Low contrast** | Light text on light background or dark on dark |
| **Excessive whitespace** | Large empty areas that waste slide/page real estate |
| **Chart/table truncation** | Data labels, axis labels, or table rows cut off |

### Step 4: Self-correct (max 3 rounds)

If defects are found:

1. Identify the root cause in the generation code (e.g., font size too large, shape position overlapping)
2. Fix the generation code
3. Re-generate the document
4. Re-render and re-inspect

After 3 rounds, deliver the best result regardless.

### Step 5: Deliver

Deliver the final document file and attach the preview PNG(s) so the user can see the visual result directly in chat.
