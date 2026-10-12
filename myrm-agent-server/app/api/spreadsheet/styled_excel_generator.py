"""
[INPUT]
openpyxl::Workbook
openpyxl.styles::Font, PatternFill, Alignment, Border, Side
app.api.spreadsheet.models::SpreadsheetGenerateRequest, SpreadsheetTheme, ColumnType, SpreadsheetColumn

[OUTPUT]
- generate_styled_excel: Converts structured spreadsheet request to styled XLSX binary bytes

[POS]
Publication-grade Excel formatting engine for HighAestheticStyledSpreadsheetGeneratorAndMultiOfficeSyncPipeline.
Single file < 250 lines. Zero `Any` types.
"""

import io
from typing import Dict, List, Tuple, Union

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.api.spreadsheet.models import (
    ColumnType,
    SpreadsheetGenerateRequest,
    SpreadsheetTheme,
)

ThemePalette = Dict[str, str]

THEME_PALETTES: Dict[SpreadsheetTheme, ThemePalette] = {
    SpreadsheetTheme.BUSINESS_NAVY: {
        "title_bg": "1F4E79",
        "title_fg": "FFFFFF",
        "header_bg": "2E5B82",
        "header_fg": "FFFFFF",
        "zebra_bg": "F2F7FA",
        "border": "D9E1E8",
    },
    SpreadsheetTheme.DARK_GOLD: {
        "title_bg": "1C1917",
        "title_fg": "F59E0B",
        "header_bg": "292524",
        "header_fg": "FDE68A",
        "zebra_bg": "FAFAF9",
        "border": "E7E5E4",
    },
    SpreadsheetTheme.FINANCIAL_EMERALD: {
        "title_bg": "14532D",
        "title_fg": "FFFFFF",
        "header_bg": "166534",
        "header_fg": "FFFFFF",
        "zebra_bg": "F0FDF4",
        "border": "DCFCE7",
    },
    SpreadsheetTheme.TECH_SLATE: {
        "title_bg": "0F172A",
        "title_fg": "38BDF8",
        "header_bg": "1E293B",
        "header_fg": "F1F5F9",
        "zebra_bg": "F8FAFC",
        "border": "E2E8F0",
    },
}


def _calc_char_width(text: str) -> float:
    """Calculate display width considering wide East-Asian characters."""
    width = 0.0
    for ch in text:
        # Ordinal > 127 is usually full-width Chinese/Japanese/Korean
        width += 2.0 if ord(ch) > 127 else 1.15
    return width


def _format_cell_value(
    val: Union[str, int, float, bool, None],
    col_type: ColumnType,
) -> Tuple[Union[str, int, float, bool, None], str, str]:
    """Returns (coerced_value, num_format, horizontal_alignment)."""
    if val is None or val == "":
        return None, "@", "left"

    if col_type == ColumnType.NUMBER:
        try:
            num = float(val) if isinstance(val, str) else float(val)
            return (int(num) if num.is_integer() else num, "#,##0.00", "right")
        except (ValueError, TypeError):
            return str(val), "@", "right"

    if col_type == ColumnType.CURRENCY:
        try:
            num = float(val) if isinstance(val, str) else float(val)
            return (num, "¥#,##0.00", "right")
        except (ValueError, TypeError):
            return str(val), "@", "right"

    if col_type == ColumnType.PERCENTAGE:
        try:
            num = float(val) if isinstance(val, str) else float(val)
            # If percentage is passed like 0.15 or 15
            val_flt = num / 100.0 if num > 1.0 else num
            return (val_flt, "0.0%", "right")
        except (ValueError, TypeError):
            return str(val), "@", "right"

    if col_type == ColumnType.DATE:
        return str(val), "yyyy-mm-dd", "center"

    return str(val), "@", "left"


def generate_styled_excel(request: SpreadsheetGenerateRequest) -> bytes:
    """Render publication-grade Excel spreadsheet with high-end typography & colors."""
    wb = Workbook()
    ws = wb.active
    ws.title = request.sheet_name[:31]

    palette = THEME_PALETTES.get(request.theme, THEME_PALETTES[SpreadsheetTheme.BUSINESS_NAVY])
    num_cols = len(request.columns)
    if num_cols == 0:
        output = io.BytesIO()
        wb.save(output)
        return output.getvalue()

    thin_border_side = Side(border_style="thin", color=palette["border"])
    cell_border = Border(
        left=thin_border_side,
        right=thin_border_side,
        top=thin_border_side,
        bottom=thin_border_side,
    )

    # 1. Title Banner Row (Row 1)
    ws.row_dimensions[1].height = 36.0
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=num_cols)
    title_cell = ws.cell(row=1, column=1, value=request.title)
    title_cell.font = Font(name="Calibri", size=15, bold=True, color=palette["title_fg"])
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    title_fill = PatternFill(start_color=palette["title_bg"], end_color=palette["title_bg"], fill_type="solid")
    title_cell.fill = title_fill

    for c in range(1, num_cols + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = title_fill
        cell.border = cell_border

    # 2. Header Columns Row (Row 2)
    ws.row_dimensions[2].height = 28.0
    header_fill = PatternFill(start_color=palette["header_bg"], end_color=palette["header_bg"], fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color=palette["header_fg"])

    col_widths: List[float] = []
    for idx, col in enumerate(request.columns, start=1):
        cell = ws.cell(row=2, column=idx, value=col.label)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = cell_border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        col_widths.append(float(col.width) if col.width else max(12.0, _calc_char_width(col.label) + 4.0))

    # 3. Data Rows (Row 3 onwards)
    data_font = Font(name="Calibri", size=10, color="0F172A")
    white_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
    zebra_fill = PatternFill(start_color=palette["zebra_bg"], end_color=palette["zebra_bg"], fill_type="solid")

    for r_idx, row in enumerate(request.rows, start=3):
        ws.row_dimensions[r_idx].height = 22.0
        is_even = (r_idx - 3) % 2 == 1
        current_fill = zebra_fill if is_even else white_fill

        for c_idx, col in enumerate(request.columns, start=1):
            raw_val = row.cells.get(col.key)
            coerced_val, num_fmt, horiz_align = _format_cell_value(raw_val, col.col_type)

            cell = ws.cell(row=r_idx, column=c_idx, value=coerced_val)
            cell.font = data_font
            cell.fill = current_fill
            cell.border = cell_border
            cell.alignment = Alignment(horizontal=horiz_align, vertical="center")
            if num_fmt != "@":
                cell.number_format = num_fmt

            # Track dynamic column width
            val_str = str(raw_val) if raw_val is not None else ""
            char_w = _calc_char_width(val_str) + 3.5
            if char_w > col_widths[c_idx - 1]:
                col_widths[c_idx - 1] = min(char_w, 48.0)

    # Set Column Widths
    for c_idx, width in enumerate(col_widths, start=1):
        col_letter = get_column_letter(c_idx)
        ws.column_dimensions[col_letter].width = max(width, 12.0)

    # 4. View Configuration: Freeze panes on header row + keep grid lines
    ws.freeze_panes = "A3"
    if ws.views.sheetView:
        ws.views.sheetView[0].showGridLines = True

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()
