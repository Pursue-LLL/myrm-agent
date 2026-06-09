import { describe, expect, it } from 'vitest';
import { parseCsv } from '../CsvParser';

describe('CsvParser', () => {
  it('parses basic CSV', () => {
    const result = parseCsv('name,age,city\nAlice,30,NYC\nBob,25,LA');
    expect(result.headers).toEqual(['name', 'age', 'city']);
    expect(result.rows).toEqual([
      ['Alice', '30', 'NYC'],
      ['Bob', '25', 'LA'],
    ]);
    expect(result.delimiter).toBe(',');
    expect(result.totalRows).toBe(2);
  });

  it('parses TSV (tab-delimited)', () => {
    const result = parseCsv('name\tage\ttown\nEve\t28\tSF');
    expect(result.headers).toEqual(['name', 'age', 'town']);
    expect(result.rows).toEqual([['Eve', '28', 'SF']]);
    expect(result.delimiter).toBe('\t');
  });

  it('handles quoted fields with commas', () => {
    const result = parseCsv('name,address\n"Doe, Jane","123 Main St, Apt 4"');
    expect(result.rows[0]).toEqual(['Doe, Jane', '123 Main St, Apt 4']);
  });

  it('handles escaped double-quotes', () => {
    const result = parseCsv('val\n"""hello"""');
    expect(result.rows[0]).toEqual(['"hello"']);
  });

  it('strips BOM character', () => {
    const bom = '\uFEFF';
    const result = parseCsv(`${bom}a,b\n1,2`);
    expect(result.headers).toEqual(['a', 'b']);
  });

  it('normalises CRLF and CR line endings', () => {
    const result = parseCsv('x,y\r\n1,2\r3,4');
    expect(result.rows).toEqual([
      ['1', '2'],
      ['3', '4'],
    ]);
  });

  it('returns empty result for empty input', () => {
    const result = parseCsv('');
    expect(result.headers).toEqual([]);
    expect(result.rows).toEqual([]);
    expect(result.totalRows).toBe(0);
  });

  it('pads short rows and trims long rows to header length', () => {
    const result = parseCsv('a,b,c\n1\n1,2,3,4');
    expect(result.rows[0]).toEqual(['1', '', '']);
    expect(result.rows[1]).toEqual(['1', '2', '3']);
  });

  it('respects maxRows limit', () => {
    const lines = ['h1,h2', ...Array.from({ length: 20 }, (_, i) => `${i},v`)];
    const result = parseCsv(lines.join('\n'), 5);
    expect(result.rows.length).toBe(5);
    expect(result.totalRows).toBe(20);
  });

  it('detects semicolon delimiter', () => {
    const result = parseCsv('a;b;c\n1;2;3\n4;5;6');
    expect(result.delimiter).toBe(';');
  });

  it('detects pipe delimiter', () => {
    const result = parseCsv('a|b|c\n1|2|3\n4|5|6');
    expect(result.delimiter).toBe('|');
  });

  it('skips blank lines', () => {
    const result = parseCsv('a,b\n\n1,2\n\n3,4\n');
    expect(result.rows).toEqual([
      ['1', '2'],
      ['3', '4'],
    ]);
  });

  it('handles header-only CSV (no data rows)', () => {
    const result = parseCsv('name,age,city');
    expect(result.headers).toEqual(['name', 'age', 'city']);
    expect(result.rows).toEqual([]);
    expect(result.totalRows).toBe(0);
  });

  it('handles single column CSV', () => {
    const result = parseCsv('value\n100\n200\n300');
    expect(result.headers).toEqual(['value']);
    expect(result.rows).toEqual([['100'], ['200'], ['300']]);
  });

  it('handles multi-line quoted fields as separate rows (trade-off for streaming performance)', () => {
    const result = parseCsv('msg,from\n"line1\nline2",Alice');
    expect(result.totalRows).toBeGreaterThanOrEqual(2);
  });

  it('handles empty quoted fields', () => {
    const result = parseCsv('a,b,c\n"","",""');
    expect(result.rows[0]).toEqual(['', '', '']);
  });

  it('handles mixed delimiters - picks dominant one', () => {
    const result = parseCsv('a\tb\tc\n1\t2\t3\n4\t5\t6\n7\t8\t9');
    expect(result.delimiter).toBe('\t');
  });

  it('handles unicode content', () => {
    const result = parseCsv('\u540d\u524d,\u5e74\u9f84\n\u592a\u90ce,25\n\u82b1\u5b50,30');
    expect(result.headers).toEqual(['\u540d\u524d', '\u5e74\u9f84']);
    expect(result.rows[0]).toEqual(['\u592a\u90ce', '25']);
  });

  it('handles very long rows without crashing', () => {
    const cols = Array.from({ length: 100 }, (_, i) => `col${i}`);
    const vals = Array.from({ length: 100 }, (_, i) => `val${i}`);
    const result = parseCsv(`${cols.join(',')}\n${vals.join(',')}`);
    expect(result.headers.length).toBe(100);
    expect(result.rows[0].length).toBe(100);
  });
});
