import { describe, expect, it } from 'vitest';
import { xlsxToUniverData, univerDataToXlsx, type WorkbookSnapshot } from '../index';

async function createSimpleXlsx(data: unknown[][]): Promise<ArrayBuffer> {
  const XLSX = await import('xlsx');
  const ws = XLSX.utils.aoa_to_sheet(data);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Sheet1');
  const buf = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
  return new Uint8Array(buf).buffer;
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
