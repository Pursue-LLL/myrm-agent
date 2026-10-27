/**
 * Column widths of the spreadsheet grid.
 *
 * [INPUT]
 * - headers / rows: the table to lay out
 *
 * [OUTPUT]
 * - computeColumnWidths: one pixel width per column, the same for the header and every row
 *
 * [POS]
 * Cells sized by their own text start at different places in every row and the columns drift out of line, so the
 * grid sizes each column once, from the header and the first rows, and gives that width to all of its cells.
 */

const MIN_WIDTH = 72;
const MAX_WIDTH = 320;
/** Rows looked at: enough to tell what a column holds, few enough that a huge file costs no more than a small one. */
const SAMPLE_ROWS = 200;
/** Horizontal padding and borders of a cell. */
const CELL_PADDING = 28;
/** Room the header keeps for the sort arrow. */
const SORT_ARROW = 16;
const NARROW_CHAR = 7;
const WIDE_CHAR = 13;
/** Past this many characters a cell is wider than the maximum anyway, so the rest is not measured. */
const MEASURED_CHARS = Math.ceil(MAX_WIDTH / NARROW_CHAR);

function isWide(codePoint: number): boolean {
  return (
    (codePoint >= 0x1100 && codePoint <= 0x115f) ||
    (codePoint >= 0x2e80 && codePoint <= 0xa4cf) ||
    (codePoint >= 0xac00 && codePoint <= 0xd7a3) ||
    (codePoint >= 0xf900 && codePoint <= 0xfaff) ||
    (codePoint >= 0xff00 && codePoint <= 0xff60) ||
    (codePoint >= 0xffe0 && codePoint <= 0xffe6) ||
    (codePoint >= 0x1f300 && codePoint <= 0x1faff)
  );
}

function textWidth(text: string): number {
  let width = 0;
  for (const char of text.slice(0, MEASURED_CHARS)) {
    width += isWide(char.codePointAt(0) ?? 0) ? WIDE_CHAR : NARROW_CHAR;
  }
  return width;
}

export function computeColumnWidths(headers: string[], rows: string[][]): number[] {
  const sample = rows.slice(0, SAMPLE_ROWS);
  return headers.map((header, column) => {
    let width = textWidth(header) + SORT_ARROW;
    for (const row of sample) {
      width = Math.max(width, textWidth(row[column] ?? ''));
    }
    return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, width + CELL_PADDING));
  });
}
