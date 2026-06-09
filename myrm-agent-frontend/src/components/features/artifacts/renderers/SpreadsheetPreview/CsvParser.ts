/**
 * RFC 4180-compliant CSV/TSV parser with auto-delimiter detection and BOM stripping.
 */

export interface ParseResult {
  headers: string[];
  rows: string[][];
  delimiter: string;
  totalRows: number;
}

type Delimiter = ',' | '\t' | ';' | '|';

const DELIMITERS: Delimiter[] = [',', '\t', ';', '|'];
const BOM = '\uFEFF';

function detectDelimiter(text: string): Delimiter {
  const sampleLines = text.split('\n', 5);
  let best: Delimiter = ',';
  let bestScore = 0;

  for (const d of DELIMITERS) {
    const counts = sampleLines.map((line) => {
      let count = 0;
      let inQuotes = false;
      for (const ch of line) {
        if (ch === '"') inQuotes = !inQuotes;
        else if (ch === d && !inQuotes) count++;
      }
      return count;
    });
    const nonZero = counts.filter((c) => c > 0);
    if (nonZero.length === 0) continue;
    const consistent = nonZero.every((c) => c === nonZero[0]);
    const score = (consistent ? 100 : 0) + nonZero[0] * nonZero.length;
    if (score > bestScore) {
      bestScore = score;
      best = d;
    }
  }
  return best;
}

function parseLine(line: string, delimiter: string): string[] {
  const cells: string[] = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (line[i + 1] === '"') {
          current += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        current += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === delimiter) {
      cells.push(current);
      current = '';
    } else {
      current += ch;
    }
  }
  cells.push(current);
  return cells;
}

export function parseCsv(text: string, maxRows = 10_000): ParseResult {
  let content = text.startsWith(BOM) ? text.slice(1) : text;
  content = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

  const delimiter = detectDelimiter(content);
  const rawLines = content.split('\n').filter((line) => line.trim().length > 0);

  if (rawLines.length === 0) {
    return { headers: [], rows: [], delimiter, totalRows: 0 };
  }

  const headers = parseLine(rawLines[0], delimiter);
  const totalRows = rawLines.length - 1;
  const dataLines = rawLines.slice(1, maxRows + 1);

  const rows = dataLines.map((line) => {
    const cells = parseLine(line, delimiter);
    while (cells.length < headers.length) cells.push('');
    if (cells.length > headers.length) cells.length = headers.length;
    return cells;
  });

  return { headers, rows, delimiter, totalRows };
}
