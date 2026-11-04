/**
 * Spreadsheet column letters.
 *
 * [INPUT]
 * - index: zero-based column index
 *
 * [OUTPUT]
 * - columnLabel: the spreadsheet-style letters for that column (0 -> A, 25 -> Z, 26 -> AA)
 *
 * [POS]
 * Stands in for a missing header cell in the grid and in the row quoted to the composer, so both name a column the
 * same way and neither needs a translated word for it.
 */

export function columnLabel(index: number): string {
  let label = '';
  let n = index;
  do {
    label = String.fromCharCode(65 + (n % 26)) + label;
    n = Math.floor(n / 26) - 1;
  } while (n >= 0);
  return label;
}
