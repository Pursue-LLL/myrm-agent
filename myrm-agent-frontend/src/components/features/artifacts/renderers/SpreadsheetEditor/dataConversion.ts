/**
 * [INPUT]
 * `xlsx`（POS: SheetJS XLSX 读写工具）
 * [OUTPUT]
 * `xlsxToUniverData`, `univerDataToXlsx`, `UniverCellData`, `UniverSheetData`, `WorkbookSnapshot`, `FidelityWarnings`
 * [POS]
 * Univer Sheet 与 XLSX 数据结构互相转换的核心纯逻辑
 */

export interface UniverCellData {
  v: unknown;
  t?: number;
  f?: string;
  s?: Record<string, unknown>;
  /** SheetJS number format string (e.g. "0.00%", "yyyy-mm-dd") */
  numFmt?: string;
}

export interface UniverSheetData {
  id?: string;
  name?: string;
  cellData?: Record<number, Record<number, UniverCellData>>;
  mergeData?: Array<{ startRow: number; endRow: number; startColumn: number; endColumn: number }>;
  rowCount?: number;
  columnCount?: number;
}

export interface WorkbookSnapshot {
  sheets: Record<string, UniverSheetData>;
  sheetOrder: string[];
}

export interface FidelityWarnings {
  hasCharts: boolean;
  hasMacros: boolean;
  hasPivotTables: boolean;
  hasImages: boolean;
}

function mapSheetJSTypeToUniver(t: string | undefined): number {
  switch (t) {
    case 'n':
      return 2;
    case 'b':
      return 3;
    case 'd':
      return 2;
    default:
      return 1;
  }
}

function mapSheetJSStyleToUniver(s: Record<string, unknown> | undefined): Record<string, unknown> | undefined {
  if (!s) {
    return undefined;
  }
  const style: Record<string, unknown> = {};

  const font = s.font as Record<string, unknown> | undefined;
  if (font) {
    if (font.bold) {
      style.bl = 1;
    }
    if (font.italic) {
      style.it = 1;
    }
    if (font.underline) {
      style.ul = { s: 1 };
    }
    if (font.strike) {
      style.st = { s: 1 };
    }
    if (font.sz) {
      style.fs = font.sz;
    }
    if (font.name) {
      style.ff = font.name;
    }
    const fontColor = font.color as Record<string, unknown> | undefined;
    if (fontColor?.rgb) {
      style.cl = { rgb: `#${fontColor.rgb}` };
    }
  }

  const fill = s.fill as Record<string, unknown> | undefined;
  if (fill) {
    const fgColor = fill.fgColor as Record<string, unknown> | undefined;
    if (fgColor?.rgb) {
      style.bg = { rgb: `#${fgColor.rgb}` };
    }
  }

  const alignment = s.alignment as Record<string, unknown> | undefined;
  if (alignment) {
    const hMap: Record<string, number> = { left: 0, center: 1, right: 2, justify: 3 };
    const vMap: Record<string, number> = { top: 0, center: 1, bottom: 2 };
    if (typeof alignment.horizontal === 'string' && alignment.horizontal in hMap) {
      style.ht = hMap[alignment.horizontal];
    }
    if (typeof alignment.vertical === 'string' && alignment.vertical in vMap) {
      style.vt = vMap[alignment.vertical];
    }
    if (alignment.wrapText) {
      style.tb = 3;
    }
  }

  return Object.keys(style).length > 0 ? style : undefined;
}

/**
 * 将 SheetJS workbook 转换为 Univer IWorkbookData 格式。
 * 直接遍历 worksheet cell 对象，保留公式、样式、合并单元格和数字格式。
 */
export async function xlsxToUniverData(
  buffer: ArrayBuffer,
): Promise<Record<string, unknown> & { _fidelityWarnings?: FidelityWarnings }> {
  const XLSX = await import('xlsx');
  const workbook = XLSX.read(new Uint8Array(buffer), { type: 'array', cellStyles: true });

  const sheets: Record<string, unknown> = {};
  const sheetOrder: string[] = [];
  const warnings: FidelityWarnings = {
    hasCharts: false,
    hasMacros: !!workbook.vbaraw,
    hasPivotTables: false,
    hasImages: false,
  };

  for (const sheetName of workbook.SheetNames) {
    const ws = workbook.Sheets[sheetName];
    if (!ws) {
      continue;
    }

    const range = XLSX.utils.decode_range(ws['!ref'] ?? 'A1');
    const rowCount = Math.max(range.e.r + 1, 100);
    const columnCount = Math.max(range.e.c + 1, 26);

    const cellData: Record<number, Record<number, UniverCellData>> = {};

    for (const addr of Object.keys(ws)) {
      if (addr.startsWith('!')) {
        continue;
      }
      const cell = ws[addr] as { v?: unknown; t?: string; f?: string; s?: Record<string, unknown>; z?: string };
      const decoded = XLSX.utils.decode_cell(addr);
      const r = decoded.r;
      const c = decoded.c;

      const isEmpty = (cell.v === undefined || cell.v === null || cell.v === '') && !cell.f;
      if (isEmpty) {
        continue;
      }

      if (!cellData[r]) {
        cellData[r] = {};
      }

      const univerCell: UniverCellData = {
        v: cell.v ?? '',
        t: mapSheetJSTypeToUniver(cell.t),
      };

      if (cell.f) {
        univerCell.f = cell.f;
      }
      if (cell.z) {
        univerCell.numFmt = cell.z;
      }

      const mappedStyle = mapSheetJSStyleToUniver(cell.s);
      if (mappedStyle) {
        univerCell.s = mappedStyle;
      }

      cellData[r][c] = univerCell;
    }

    const mergeData: UniverSheetData['mergeData'] = [];
    if (ws['!merges']) {
      for (const m of ws['!merges']) {
        mergeData.push({
          startRow: m.s.r,
          endRow: m.e.r,
          startColumn: m.s.c,
          endColumn: m.e.c,
        });
      }
    }

    if (ws['!images'] || ws['!drawings']) {
      warnings.hasImages = true;
    }

    const id = sheetName.replace(/\s/g, '_');
    sheetOrder.push(id);
    sheets[id] = {
      id,
      name: sheetName,
      cellData,
      rowCount,
      columnCount,
      ...(mergeData.length > 0 ? { mergeData } : {}),
    };
  }

  return {
    id: 'myrm-spreadsheet',
    appVersion: '0.25.0',
    name: 'Workbook',
    sheetOrder,
    sheets,
    _fidelityWarnings: warnings,
  };
}

function mapUniverTypeToSheetJS(t: number | undefined): string {
  switch (t) {
    case 2:
      return 'n';
    case 3:
      return 'b';
    default:
      return 's';
  }
}

/**
 * 从 Univer workbook snapshot 导出为 .xlsx Blob（使用 SheetJS）。
 * 保留公式、数字格式和合并单元格。
 */
export async function univerDataToXlsx(snapshot: WorkbookSnapshot): Promise<Blob> {
  const XLSX = await import('xlsx');
  const xlsxWorkbook = XLSX.utils.book_new();

  for (const sheetId of snapshot.sheetOrder) {
    const sheetData = snapshot.sheets[sheetId];
    if (!sheetData) {
      continue;
    }

    const cellData = sheetData.cellData;
    if (!cellData) {
      XLSX.utils.book_append_sheet(xlsxWorkbook, XLSX.utils.aoa_to_sheet([]), String(sheetData.name ?? sheetId));
      continue;
    }

    const ws: Record<string, unknown> = {};
    let maxRow = 0;
    let maxCol = 0;

    const rowIndices = Object.keys(cellData)
      .map(Number)
      .sort((a, b) => a - b);
    for (const ri of rowIndices) {
      const row = cellData[ri];
      if (!row) {
        continue;
      }
      if (ri >= maxRow) {
        maxRow = ri + 1;
      }

      const colIndices = Object.keys(row)
        .map(Number)
        .sort((a, b) => a - b);
      for (const ci of colIndices) {
        if (ci >= maxCol) {
          maxCol = ci + 1;
        }
        const uCell = row[ci];
        if (!uCell) {
          continue;
        }

        const addr = XLSX.utils.encode_cell({ r: ri, c: ci });
        const sjsCell: Record<string, unknown> = {
          v: uCell.v,
          t: mapUniverTypeToSheetJS(uCell.t),
        };

        if (uCell.f) {
          sjsCell.f = uCell.f;
        }
        if (uCell.numFmt) {
          sjsCell.z = uCell.numFmt;
        }

        ws[addr] = sjsCell;
      }
    }

    ws['!ref'] = XLSX.utils.encode_range({
      s: { r: 0, c: 0 },
      e: { r: Math.max(maxRow - 1, 0), c: Math.max(maxCol - 1, 0) },
    });

    if (sheetData.mergeData && sheetData.mergeData.length > 0) {
      ws['!merges'] = sheetData.mergeData.map((m) => ({
        s: { r: m.startRow, c: m.startColumn },
        e: { r: m.endRow, c: m.endColumn },
      }));
    }

    XLSX.utils.book_append_sheet(xlsxWorkbook, ws, String(sheetData.name ?? sheetId));
  }

  const wbout = XLSX.write(xlsxWorkbook, { bookType: 'xlsx', type: 'array' });
  return new Blob([wbout], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}
