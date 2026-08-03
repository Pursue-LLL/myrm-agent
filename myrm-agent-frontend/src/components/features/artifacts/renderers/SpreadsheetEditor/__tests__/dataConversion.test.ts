import { describe, expect, it } from 'vitest';
import { xlsxToUniverData, univerDataToXlsx, type WorkbookSnapshot, type UniverCellData, type UniverSheetData } from '../index';

type FidelityWarnings = { hasCharts: boolean; hasMacros: boolean; hasPivotTables: boolean; hasImages: boolean };

async function createSimpleXlsx(data: unknown[][]): Promise<ArrayBuffer> {
  const XLSX = await import('xlsx');
  const ws = XLSX.utils.aoa_to_sheet(data);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Sheet1');
  const buf = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
  return new Uint8Array(buf).buffer;
}

async function createXlsxWithFormulas(): Promise<ArrayBuffer> {
  const XLSX = await import('xlsx');
  const ws: Record<string, unknown> = {};
  ws['A1'] = { v: 10, t: 'n' };
  ws['A2'] = { v: 20, t: 'n' };
  ws['A3'] = { v: 30, t: 'n', f: 'SUM(A1:A2)' };
  ws['B1'] = { v: 0.35, t: 'n', z: '0.00%' };
  ws['!ref'] = 'A1:B3';
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Sheet1');
  return new Uint8Array(XLSX.write(wb, { bookType: 'xlsx', type: 'array' })).buffer;
}

async function createXlsxWithMerges(): Promise<ArrayBuffer> {
  const XLSX = await import('xlsx');
  const ws = XLSX.utils.aoa_to_sheet([['Title', '', ''], ['a', 'b', 'c']]);
  ws['!merges'] = [{ s: { r: 0, c: 0 }, e: { r: 0, c: 2 } }];
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Sheet1');
  return new Uint8Array(XLSX.write(wb, { bookType: 'xlsx', type: 'array' })).buffer;
}

async function createMultiSheetXlsx(
  sheets: Array<{ name: string; data: unknown[][] }>,
): Promise<ArrayBuffer> {
  const XLSX = await import('xlsx');
  const wb = XLSX.utils.book_new();
  for (const s of sheets) {
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(s.data), s.name);
  }
  return new Uint8Array(XLSX.write(wb, { bookType: 'xlsx', type: 'array' })).buffer;
}

describe('xlsxToUniverData', () => {
  it('maps string cells to type 1', async () => {
    const buf = await createSimpleXlsx([['hello']]);
    const result = (await xlsxToUniverData(buf)) as { sheets: Record<string, { cellData: Record<number, Record<number, { v: unknown; t?: number }>> }> };
    const cell = result.sheets['Sheet1']?.cellData[0]?.[0];
    expect(cell).toBeDefined();
    expect(cell!.v).toBe('hello');
    expect(cell!.t).toBe(1);
  });

  it('maps number cells to type 2', async () => {
    const buf = await createSimpleXlsx([[42]]);
    const result = (await xlsxToUniverData(buf)) as { sheets: Record<string, { cellData: Record<number, Record<number, { v: unknown; t?: number }>> }> };
    const cell = result.sheets['Sheet1']?.cellData[0]?.[0];
    expect(cell).toBeDefined();
    expect(cell!.v).toBe(42);
    expect(cell!.t).toBe(2);
  });

  it('maps boolean cells to type 3', async () => {
    const buf = await createSimpleXlsx([[true]]);
    const result = (await xlsxToUniverData(buf)) as { sheets: Record<string, { cellData: Record<number, Record<number, { v: unknown; t?: number }>> }> };
    const cell = result.sheets['Sheet1']?.cellData[0]?.[0];
    expect(cell).toBeDefined();
    expect(cell!.v).toBe(true);
    expect(cell!.t).toBe(3);
  });

  it('skips empty/null/undefined cells', async () => {
    const buf = await createSimpleXlsx([['a', '', 'b']]);
    const result = (await xlsxToUniverData(buf)) as { sheets: Record<string, { cellData: Record<number, Record<number, { v: unknown }>> }> };
    const row = result.sheets['Sheet1']?.cellData[0];
    expect(row?.[0]).toBeDefined();
    expect(row?.[1]).toBeUndefined();
    expect(row?.[2]).toBeDefined();
  });

  it('handles multiple sheets and preserves order', async () => {
    const buf = await createMultiSheetXlsx([
      { name: 'Alpha', data: [['a1']] },
      { name: 'Beta', data: [['b1']] },
    ]);
    const result = (await xlsxToUniverData(buf)) as { sheetOrder: string[] };
    expect(result.sheetOrder).toEqual(['Alpha', 'Beta']);
  });

  it('replaces spaces in sheet names for IDs', async () => {
    const buf = await createMultiSheetXlsx([
      { name: 'My Sheet', data: [['x']] },
    ]);
    const result = (await xlsxToUniverData(buf)) as { sheetOrder: string[]; sheets: Record<string, { id: string; name: string }> };
    expect(result.sheetOrder).toEqual(['My_Sheet']);
    expect(result.sheets['My_Sheet']?.id).toBe('My_Sheet');
    expect(result.sheets['My_Sheet']?.name).toBe('My Sheet');
  });

  it('enforces minimum rowCount=100 and columnCount=26', async () => {
    const buf = await createSimpleXlsx([['single']]);
    const result = (await xlsxToUniverData(buf)) as { sheets: Record<string, { rowCount: number; columnCount: number }> };
    const sheet = result.sheets['Sheet1']!;
    expect(sheet.rowCount).toBeGreaterThanOrEqual(100);
    expect(sheet.columnCount).toBeGreaterThanOrEqual(26);
  });

  it('uses actual row/column count when exceeding minimums', async () => {
    const rows: unknown[][] = [];
    for (let r = 0; r < 150; r++) {
      const row: unknown[] = [];
      for (let c = 0; c < 30; c++) {
        row.push(`r${r}c${c}`);
      }
      rows.push(row);
    }
    const buf = await createSimpleXlsx(rows);
    const result = (await xlsxToUniverData(buf)) as { sheets: Record<string, { rowCount: number; columnCount: number }> };
    const sheet = result.sheets['Sheet1']!;
    expect(sheet.rowCount).toBe(150);
    expect(sheet.columnCount).toBe(30);
  });

  it('returns correct top-level structure', async () => {
    const buf = await createSimpleXlsx([['a']]);
    const result = await xlsxToUniverData(buf);
    expect(result).toHaveProperty('id', 'myrm-spreadsheet');
    expect(result).toHaveProperty('appVersion', '0.25.0');
    expect(result).toHaveProperty('name', 'Workbook');
    expect(result).toHaveProperty('sheetOrder');
    expect(result).toHaveProperty('sheets');
  });
});

describe('univerDataToXlsx', () => {
  it('round-trips basic data (xlsx → univer → xlsx → univer)', async () => {
    const original = [['Name', 'Age'], ['Alice', 30], ['Bob', 25]];
    const buf = await createSimpleXlsx(original);
    const univerData = (await xlsxToUniverData(buf)) as WorkbookSnapshot;
    const blob = await univerDataToXlsx(univerData);
    const roundTrip = await xlsxToUniverData(await blob.arrayBuffer());
    const rt = roundTrip as { sheets: Record<string, { cellData: Record<number, Record<number, { v: unknown }>> }> };
    expect(rt.sheets['Sheet1']?.cellData[0]?.[0]?.v).toBe('Name');
    expect(rt.sheets['Sheet1']?.cellData[1]?.[0]?.v).toBe('Alice');
    expect(rt.sheets['Sheet1']?.cellData[1]?.[1]?.v).toBe(30);
  });

  it('handles empty sheet (no cellData)', async () => {
    const snapshot: WorkbookSnapshot = {
      sheetOrder: ['s1'],
      sheets: { s1: { name: 'Empty' } },
    };
    const blob = await univerDataToXlsx(snapshot);
    expect(blob.size).toBeGreaterThan(0);
    expect(blob.type).toBe('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
  });

  it('skips missing sheet in sheetOrder', async () => {
    const snapshot: WorkbookSnapshot = {
      sheetOrder: ['exists', 'ghost'],
      sheets: { exists: { name: 'Exists', cellData: { 0: { 0: { v: 'ok' } } } } },
    };
    const blob = await univerDataToXlsx(snapshot);
    expect(blob.size).toBeGreaterThan(0);
  });

  it('preserves sheet order in export', async () => {
    const snapshot: WorkbookSnapshot = {
      sheetOrder: ['second', 'first'],
      sheets: {
        first: { name: 'First', cellData: { 0: { 0: { v: 'f1' } } } },
        second: { name: 'Second', cellData: { 0: { 0: { v: 's1' } } } },
      },
    };
    const blob = await univerDataToXlsx(snapshot);
    const XLSX = await import('xlsx');
    const wb = XLSX.read(await blob.arrayBuffer(), { type: 'array' });
    expect(wb.SheetNames).toEqual(['Second', 'First']);
  });

  it('handles sparse cell data correctly', async () => {
    const snapshot: WorkbookSnapshot = {
      sheetOrder: ['s1'],
      sheets: {
        s1: {
          name: 'Sparse',
          cellData: {
            0: { 0: { v: 'A1' }, 5: { v: 'F1' } },
            10: { 3: { v: 'D11' } },
          },
        },
      },
    };
    const blob = await univerDataToXlsx(snapshot);
    const rt = (await xlsxToUniverData(await blob.arrayBuffer())) as {
      sheets: Record<string, { cellData: Record<number, Record<number, { v: unknown }>> }>;
    };
    const sheet = rt.sheets['Sparse']!;
    expect(sheet.cellData[0]?.[0]?.v).toBe('A1');
    expect(sheet.cellData[0]?.[5]?.v).toBe('F1');
    expect(sheet.cellData[10]?.[3]?.v).toBe('D11');
  });

  it('produces valid xlsx blob', async () => {
    const snapshot: WorkbookSnapshot = {
      sheetOrder: ['s1'],
      sheets: { s1: { name: 'Test', cellData: { 0: { 0: { v: 'hello' } } } } },
    };
    const blob = await univerDataToXlsx(snapshot);
    expect(blob.type).toBe('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    const XLSX = await import('xlsx');
    const wb = XLSX.read(await blob.arrayBuffer(), { type: 'array' });
    expect(wb.SheetNames).toContain('Test');
    const ws = wb.Sheets['Test'];
    expect(ws?.['A1']?.v).toBe('hello');
  });
});

describe('formula roundtrip', () => {
  it('preserves formulas through xlsx → univer → xlsx cycle', async () => {
    const buf = await createXlsxWithFormulas();
    const univerData = await xlsxToUniverData(buf);
    const sheets = (univerData as { sheets: Record<string, { cellData: Record<number, Record<number, UniverCellData>> }> }).sheets;

    const a3 = sheets['Sheet1']?.cellData[2]?.[0];
    expect(a3?.f).toBe('SUM(A1:A2)');

    const blob = await univerDataToXlsx(univerData as WorkbookSnapshot);
    const XLSX = await import('xlsx');
    const wb = XLSX.read(await blob.arrayBuffer(), { type: 'array' });
    const ws = wb.Sheets['Sheet1'];
    expect(ws?.['A3']?.f).toBe('SUM(A1:A2)');
  });

  it('preserves number format (numFmt) on import', async () => {
    const buf = await createXlsxWithFormulas();
    const univerData = await xlsxToUniverData(buf);
    const sheets = (univerData as { sheets: Record<string, { cellData: Record<number, Record<number, UniverCellData>> }> }).sheets;

    const b1 = sheets['Sheet1']?.cellData[0]?.[1];
    expect(b1?.numFmt).toBe('0.00%');
  });

  it('preserves numFmt in exported snapshot for Univer rendering', async () => {
    const snapshot: WorkbookSnapshot = {
      sheetOrder: ['s1'],
      sheets: {
        s1: {
          name: 'Test',
          cellData: { 0: { 0: { v: 0.35, t: 2, numFmt: '0.00%' } } },
        },
      },
    };
    const blob = await univerDataToXlsx(snapshot);
    expect(blob.size).toBeGreaterThan(0);
    const XLSX = await import('xlsx');
    const wb = XLSX.read(await blob.arrayBuffer(), { type: 'array' });
    const ws = wb.Sheets['Test'];
    expect(ws?.['A1']?.v).toBe(0.35);
  });
});

describe('merge roundtrip', () => {
  it('preserves merged cells through xlsx → univer → xlsx cycle', async () => {
    const buf = await createXlsxWithMerges();
    const univerData = await xlsxToUniverData(buf);
    const sheets = (univerData as { sheets: Record<string, { mergeData?: Array<{ startRow: number; endRow: number; startColumn: number; endColumn: number }> }> }).sheets;

    expect(sheets['Sheet1']?.mergeData).toHaveLength(1);
    expect(sheets['Sheet1']?.mergeData?.[0]).toEqual({
      startRow: 0, endRow: 0, startColumn: 0, endColumn: 2,
    });

    const blob = await univerDataToXlsx(univerData as WorkbookSnapshot);
    const XLSX = await import('xlsx');
    const wb = XLSX.read(await blob.arrayBuffer(), { type: 'array' });
    const ws = wb.Sheets['Sheet1'];
    expect(ws?.['!merges']).toHaveLength(1);
    expect(ws?.['!merges']?.[0]).toEqual(
      expect.objectContaining({ s: { r: 0, c: 0 }, e: { r: 0, c: 2 } }),
    );
  });
});

describe('fidelity warnings', () => {
  it('returns no warnings for plain xlsx', async () => {
    const buf = await createSimpleXlsx([['plain']]);
    const result = await xlsxToUniverData(buf);
    const warnings = (result as Record<string, unknown>)._fidelityWarnings as { hasMacros: boolean; hasCharts: boolean };
    expect(warnings.hasMacros).toBe(false);
    expect(warnings.hasCharts).toBe(false);
  });

  it('_fidelityWarnings is always present', async () => {
    const buf = await createSimpleXlsx([['test']]);
    const result = await xlsxToUniverData(buf);
    expect(result).toHaveProperty('_fidelityWarnings');
    const warnings = (result as Record<string, unknown>)._fidelityWarnings as FidelityWarnings;
    expect(warnings).toMatchObject({
      hasCharts: false,
      hasMacros: false,
      hasPivotTables: false,
      hasImages: false,
    });
  });
});
