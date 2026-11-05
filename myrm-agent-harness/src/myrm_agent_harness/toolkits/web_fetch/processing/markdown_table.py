"""Markdown table layout for converted HTML tables.

[INPUT]
- (none)

[OUTPUT]
- render_markdown_table: Lays converted table rows out as a Markdown table block, with a blank header when the table has none

[POS]
Output side of HTML table conversion: html_to_markdown extracts and converts the cells, this module lays them out.
"""

from __future__ import annotations


def render_markdown_table(rows: list[list[str]], *, has_header: bool) -> str:
    """Render *rows* as a Markdown table block.

    *rows* must be non-empty and every row must hold at least one cell. Short rows are padded to the widest row.
    Markdown tables need a header line, so a table without a header row gets a blank one.
    """
    width = max(len(row) for row in rows)
    padded = [[*row, *([""] * (width - len(row)))] for row in rows]
    header, body = (padded[0], padded[1:]) if has_header else ([""] * width, padded)
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
        *("| " + " | ".join(row) + " |" for row in body),
    ]
    return "\n\n" + "\n".join(lines) + "\n\n"
