"""GFM tables as monospace boxes for Telegram HTML.

[INPUT]
- (none)

[OUTPUT]
- render_monospace_table(): One GFM table as a box-drawing table inside a ``<pre>`` block
- convert_tables(): Every GFM table of a text, replaced by the place its ``<pre>`` markup was set aside under

[POS]
Telegram HTML has no table markup, so a table is drawn in box characters inside a ``<pre>`` block. The HTML converter
sets that markup aside, so no later formatting pass touches the table.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable

_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")


def _parse_table_row(line: str) -> list[str]:
    """Split a GFM table row into stripped cell values."""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def render_monospace_table(header_row: str, data_rows: list[str]) -> str:
    """Convert a GFM table into a ``<pre>``-wrapped monospace ASCII table."""
    headers = _parse_table_row(header_row)
    parsed_rows = [_parse_table_row(row) for row in data_rows]

    col_count = len(headers)
    col_widths = [len(h) for h in headers]
    for row in parsed_rows:
        for i, cell in enumerate(row[:col_count]):
            col_widths[i] = max(col_widths[i], len(cell))

    def _fmt_row(cells: list[str]) -> str:
        padded = [cells[i].ljust(col_widths[i]) if i < len(cells) else " " * col_widths[i] for i in range(col_count)]
        return "│ " + " │ ".join(padded) + " │"

    sep_parts = ["─" * (w + 2) for w in col_widths]

    lines: list[str] = []
    lines.append("┌" + "┬".join(sep_parts) + "┐")
    lines.append(_fmt_row(headers))
    lines.append("├" + "┼".join(sep_parts) + "┤")
    for row in parsed_rows:
        lines.append(_fmt_row(row))
    lines.append("└" + "┴".join(sep_parts) + "┘")

    return "<pre>" + html.escape("\n".join(lines)) + "</pre>"


def convert_tables(text: str, keep: Callable[[str], str]) -> str:
    """Replace each GFM table of *text* by ``keep(<pre> markup)``, so the caller can protect the markup from later passes."""
    if "|" not in text or "-" not in text:
        return text

    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if "|" in line and i + 1 < len(lines) and "|" in lines[i + 1] and _TABLE_SEPARATOR_RE.match(lines[i + 1]):
            end = i + 2
            while end < len(lines) and "|" in lines[end]:
                end += 1
            if end > i + 2:
                out.append(keep(render_monospace_table(line, lines[i + 2 : end])))
                i = end
                continue
        out.append(line)
        i += 1
    return "\n".join(out)
