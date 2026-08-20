'use client';

/**
 * [INPUT]
 * `@/lib/api`::getStorageUrl（POS: API URL 拼接工具）；
 * `@univerjs/presets` + `@univerjs/preset-sheets-core`（POS: Univer Sheet 编辑器引擎）；
 * `xlsx`（POS: SheetJS XLSX 读写）。
 * [OUTPUT]
 * SpreadsheetEditor: XLSX Live 编辑器组件，支持浏览器内编辑 + 导出保存。
 * [POS]
 * Artifact Edit 模式下的 XLSX 交互编辑器；通过 SheetJS 实现 XLSX ↔ Univer 数据双向转换，无需 Pro 服务器。
 */

import React, { memo, useEffect, useRef, useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { getStorageUrl } from '@/lib/api';
import type { IDisposable } from '@univerjs/core';
import '@univerjs/preset-sheets-core/lib/index.css';

type UniverAPI = Awaited<ReturnType<(typeof import('@univerjs/presets'))['createUniver']>>['univerAPI'];

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

interface FidelityWarnings {
  hasCharts: boolean;
  hasMacros: boolean;
  hasPivotTables: boolean;
  hasImages: boolean;
}

interface SpreadsheetEditorProps {
  previewUrl: string;
  filename: string;
  onSave: (blob: Blob) => Promise<void>;
  onDirty: (dirty: boolean) => void;
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

const DRAFT_DB_NAME = 'myrm-spreadsheet-drafts';
const DRAFT_STORE = 'drafts';
const DRAFT_AUTO_SAVE_DELAY_MS = 5000;

function getDraftKey(previewUrl: string): string {
  return `draft:${previewUrl}`;
}

async function openDraftDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DRAFT_DB_NAME, 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(DRAFT_STORE);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function saveDraft(key: string, snapshot: unknown): Promise<void> {
  try {
    const db = await openDraftDB();
    const tx = db.transaction(DRAFT_STORE, 'readwrite');
    tx.objectStore(DRAFT_STORE).put(snapshot, key);
    await new Promise<void>((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch {
    /* best-effort; don't crash editor on quota/permission errors */
  }
}

async function loadDraft(key: string): Promise<unknown | null> {
  try {
    const db = await openDraftDB();
    const tx = db.transaction(DRAFT_STORE, 'readonly');
    const req = tx.objectStore(DRAFT_STORE).get(key);
    const result = await new Promise<unknown | null>((resolve, reject) => {
      req.onsuccess = () => resolve(req.result ?? null);
      req.onerror = () => reject(req.error);
    });
    db.close();
    return result;
  } catch {
    return null;
  }
}

async function deleteDraft(key: string): Promise<void> {
  try {
    const db = await openDraftDB();
    const tx = db.transaction(DRAFT_STORE, 'readwrite');
    tx.objectStore(DRAFT_STORE).delete(key);
    await new Promise<void>((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch {
    /* best-effort */
  }
}

const SpreadsheetEditor: React.FC<SpreadsheetEditorProps> = memo(({ previewUrl, filename, onSave, onDirty }) => {
  const t = useTranslations('artifacts');
  const containerRef = useRef<HTMLDivElement>(null);
  const univerRef = useRef<UniverAPI | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const [fidelityWarnings, setFidelityWarnings] = useState<FidelityWarnings | null>(null);
  const [warningDismissed, setWarningDismissed] = useState(false);
  const [hasDraftRecovery, setHasDraftRecovery] = useState(false);
  const dirtyRef = useRef(false);
  const savedTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const draftTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const draftKeyRef = useRef(getDraftKey(previewUrl));

  const scheduleDraftSave = useCallback(() => {
    clearTimeout(draftTimerRef.current);
    draftTimerRef.current = setTimeout(() => {
      const api = univerRef.current;
      if (!api || !dirtyRef.current) {
        return;
      }
      const workbook = api.getActiveWorkbook();
      if (!workbook) {
        return;
      }
      const snapshot = workbook.save();
      saveDraft(draftKeyRef.current, snapshot);
    }, DRAFT_AUTO_SAVE_DELAY_MS);
  }, []);

  const markDirty = useCallback(() => {
    if (!dirtyRef.current) {
      dirtyRef.current = true;
      onDirty(true);
    }
    scheduleDraftSave();
  }, [onDirty, scheduleDraftSave]);

  useEffect(() => {
    let disposed = false;
    let commandDisposable: IDisposable | null = null;

    const init = async () => {
      if (!containerRef.current) {
        return;
      }
      setLoading(true);
      setError(null);

      try {
        const url = getStorageUrl(previewUrl);
        const res = await fetch(url);
        if (!res.ok) {
          throw new Error(`Failed to fetch: ${res.status}`);
        }
        const buffer = await res.arrayBuffer();

        if (disposed) {
          return;
        }

        let workbookData = await xlsxToUniverData(buffer);
        const warnings = (workbookData as Record<string, unknown>)._fidelityWarnings as FidelityWarnings | undefined;
        if (warnings && (warnings.hasCharts || warnings.hasMacros || warnings.hasPivotTables || warnings.hasImages)) {
          setFidelityWarnings(warnings);
        }

        const draft = await loadDraft(draftKeyRef.current);
        if (draft && typeof draft === 'object') {
          setHasDraftRecovery(true);
          workbookData = draft as Record<string, unknown>;
        }

        const [{ createUniver, LocaleType, mergeLocales }, { UniverSheetsCorePreset }] = await Promise.all([
          import('@univerjs/presets'),
          import('@univerjs/preset-sheets-core'),
        ]);

        let localeData: Record<string, unknown> = {};
        try {
          const mod = await import('@univerjs/preset-sheets-core/locales/en-US');
          localeData = mod.default ?? mod;
        } catch {
          /* locale optional */
        }

        if (disposed || !containerRef.current) {
          return;
        }

        const { univerAPI } = createUniver({
          locale: LocaleType.EN_US,
          locales: {
            [LocaleType.EN_US]: mergeLocales(localeData as Parameters<typeof mergeLocales>[0]),
          },
          presets: [
            UniverSheetsCorePreset({
              container: containerRef.current,
            }),
          ],
        });

        univerAPI.createWorkbook(workbookData as unknown as import('@univerjs/core').IWorkbookData);
        univerRef.current = univerAPI;

        commandDisposable = univerAPI.onCommandExecuted(() => {
          if (!disposed) {
            markDirty();
          }
        });

        setLoading(false);
      } catch (err) {
        if (!disposed) {
          setError(err instanceof Error ? err.message : String(err));
          setLoading(false);
        }
      }
    };

    init();

    return () => {
      disposed = true;
      clearTimeout(draftTimerRef.current);
      commandDisposable?.dispose();
      if (univerRef.current) {
        try {
          univerRef.current.dispose();
        } catch {
          /* best-effort cleanup */
        }
        univerRef.current = null;
      }
    };
  }, [previewUrl, markDirty, retryKey]);

  const handleSave = useCallback(async () => {
    const api = univerRef.current;
    if (!api || saving) {
      return;
    }

    const workbook = api.getActiveWorkbook();
    if (!workbook) {
      return;
    }

    setSaving(true);
    setSaved(false);
    setSaveError(false);

    try {
      const snapshot = workbook.save();
      const blob = await univerDataToXlsx(snapshot as WorkbookSnapshot);
      await onSave(blob);
      dirtyRef.current = false;
      onDirty(false);
      clearTimeout(draftTimerRef.current);
      deleteDraft(draftKeyRef.current);
      setHasDraftRecovery(false);
      setSaved(true);
      clearTimeout(savedTimerRef.current);
      savedTimerRef.current = setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      console.error('Failed to save spreadsheet:', err);
      setSaveError(true);
      clearTimeout(savedTimerRef.current);
      savedTimerRef.current = setTimeout(() => setSaveError(false), 3000);
    } finally {
      setSaving(false);
    }
  }, [onSave, onDirty, saving]);

  const handleRetry = useCallback(() => {
    setError(null);
    setRetryKey((prev) => prev + 1);
  }, []);

  useEffect(() => {
    if (!dirtyRef.current) {
      return;
    }
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  });

  useEffect(() => {
    return () => clearTimeout(savedTimerRef.current);
  }, []);

  if (error) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 p-4">
        <p className="text-sm text-destructive">
          {t('spreadsheet.loadError')} {filename}
        </p>
        <p className="text-xs text-muted-foreground">{error}</p>
        <button
          onClick={handleRetry}
          className="px-4 py-1.5 text-xs font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          {t('retry')}
        </button>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full flex flex-col">
      {hasDraftRecovery && (
        <div className="shrink-0 flex items-center gap-2 px-3 py-2 bg-blue-50 dark:bg-blue-950/30 border-b border-blue-200 dark:border-blue-800 text-blue-800 dark:text-blue-200">
          <svg className="w-4 h-4 shrink-0" viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75 0 000-1.5H4.28a.75.75 0 00-.75.75v3.955a.75.75 0 001.5 0v-2.134l.312.311a7 7 0 0011.712-3.138.75.75 0 00-1.449-.399zm1.063-6.293A.75.75 0 0015.625 5v2.134l-.312-.311a7 7 0 00-11.712 3.138.75.75 0 001.449.399 5.5 5.5 0 019.201-2.466l.312.311h-2.433a.75.75 0 000 1.5h3.952a.75.75 0 00.75-.75V5.001z"
              clipRule="evenodd"
            />
          </svg>
          <span className="text-xs flex-1">{t('spreadsheet.draftRecovered')}</span>
          <button
            onClick={() => {
              deleteDraft(draftKeyRef.current);
              setHasDraftRecovery(false);
              setRetryKey((prev) => prev + 1);
            }}
            className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
          >
            {t('spreadsheet.discardDraft')}
          </button>
        </div>
      )}
      {fidelityWarnings && !warningDismissed && (
        <div className="shrink-0 flex items-center gap-2 px-3 py-2 bg-amber-50 dark:bg-amber-950/30 border-b border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200">
          <svg className="w-4 h-4 shrink-0" viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z"
              clipRule="evenodd"
            />
          </svg>
          <span className="text-xs flex-1">
            {t('spreadsheet.fidelityWarning', {
              features: [
                fidelityWarnings.hasCharts && t('spreadsheet.charts'),
                fidelityWarnings.hasMacros && t('spreadsheet.macros'),
                fidelityWarnings.hasPivotTables && t('spreadsheet.pivotTables'),
                fidelityWarnings.hasImages && t('spreadsheet.images'),
              ]
                .filter(Boolean)
                .join(', '),
            })}
          </span>
          <button
            onClick={() => setWarningDismissed(true)}
            className="shrink-0 text-amber-600 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-200"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
              <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
            </svg>
          </button>
        </div>
      )}
      {loading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-background/80">
          <div className="animate-spin w-8 h-8 border-2 border-muted-foreground/30 border-t-primary rounded-full" />
        </div>
      )}
      <div ref={containerRef} className="flex-1 min-h-0" />
      {!loading && (
        <div className="shrink-0 flex items-center justify-end gap-2 px-3 py-2 border-t border-border bg-muted/30">
          <button
            onClick={handleSave}
            disabled={saving}
            className={cn(
              'px-4 py-1.5 text-xs font-medium rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed',
              saveError
                ? 'bg-destructive text-destructive-foreground'
                : 'bg-primary text-primary-foreground hover:bg-primary/90',
            )}
          >
            {saving ? t('saving') : saved ? t('saved') : saveError ? t('retry') : t('spreadsheet.saveChanges')}
          </button>
        </div>
      )}
    </div>
  );
});

SpreadsheetEditor.displayName = 'SpreadsheetEditor';
export default SpreadsheetEditor;
