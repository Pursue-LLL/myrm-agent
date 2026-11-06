"""Markdown table layout for converted HTML tables.

[INPUT]
- (none)

[OUTPUT]
- render_markdown_table: Lays converted table rows out as a Markdown table block; the header and delimiter lines span the widest row, body rows keep their own cells, and a table without a header gets a blank one

[POS]
Output side of HTML table conversion: html_to_markdown extracts and converts the cells, this module lays them out.
"""

from __future__ import annotations


def render_markdown_table(rows: list[list[str]], *, has_header: bool) -> str:
    """Render *rows* as a Markdown table block.

    *rows* must be non-empty and every row must hold at least one cell. The header and delimiter lines span the widest
    row; a body row keeps the cells it has and the Markdown renderer fills in the rest as empty cells. Padding every
    row to the widest would make the output grow with rows times the widest row, which a page can inflate with one
    wide row and many short ones. Markdown tables need a header line, so a table without a header row gets a blank one.
    """
    width = max(len(row) for row in rows)
    header, body = (rows[0], rows[1:]) if has_header else ([], rows)
    header = [*header, *([""] * (width - len(header)))]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
        *("| " + " | ".join(row) + " |" for row in body),
    ]
    return "\n\n" + "\n".join(lines) + "\n\n"
