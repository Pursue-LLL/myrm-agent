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

type UniverAPI = Awaited<ReturnType<typeof import('@univerjs/presets')['createUniver']>>['univerAPI'];

export interface WorkbookSnapshot {
  sheets: Record<string, {
    name?: string;
    cellData?: Record<number, Record<number, { v: unknown }>>;
  }>;
  sheetOrder: string[];
}

interface SpreadsheetEditorProps {
  previewUrl: string;
  filename: string;
  onSave: (blob: Blob) => Promise<void>;
  onDirty: (dirty: boolean) => void;
}

/**
 * 将 SheetJS workbook 解析数据转换为 Univer IWorkbookData 格式。
 * 复用现有 xlsx 依赖，无需 Pro 服务器。
 */
export async function xlsxToUniverData(buffer: ArrayBuffer): Promise<Record<string, unknown>> {
  const XLSX = await import('xlsx');
  const workbook = XLSX.read(new Uint8Array(buffer), { type: 'array' });

  const sheets: Record<string, unknown> = {};
  const sheetOrder: string[] = [];

  for (const sheetName of workbook.SheetNames) {
    const ws = workbook.Sheets[sheetName];
    const json = XLSX.utils.sheet_to_json<unknown[]>(ws, { header: 1, defval: '' });
    const rows = json as unknown[][];

    const cellData: Record<number, Record<number, { v: unknown; t?: number }>> = {};
    for (let r = 0; r < rows.length; r++) {
      cellData[r] = {};
      for (let c = 0; c < rows[r].length; c++) {
        const val = rows[r][c];
        if (val !== '' && val !== null && val !== undefined) {
          cellData[r][c] = {
            v: val,
            t: typeof val === 'number' ? 2 : typeof val === 'boolean' ? 3 : 1,
          };
        }
      }
    }

    const id = sheetName.replace(/\s/g, '_');
    sheetOrder.push(id);
    sheets[id] = {
      id,
      name: sheetName,
      cellData,
      rowCount: Math.max(rows.length, 100),
      columnCount: Math.max(rows[0]?.length ?? 0, 26),
    };
  }

  return {
    id: 'myrm-spreadsheet',
    appVersion: '0.25.0',
    name: 'Workbook',
    sheetOrder,
    sheets,
  };
}

/**
 * 从 Univer workbook snapshot 导出为 .xlsx Blob（使用 SheetJS）。
 */
export async function univerDataToXlsx(snapshot: WorkbookSnapshot): Promise<Blob> {
  const XLSX = await import('xlsx');
  const xlsxWorkbook = XLSX.utils.book_new();

  for (const sheetId of snapshot.sheetOrder) {
    const sheetData = snapshot.sheets[sheetId];
    if (!sheetData) continue;

    const cellData = sheetData.cellData;
    if (!cellData) {
      XLSX.utils.book_append_sheet(xlsxWorkbook, XLSX.utils.aoa_to_sheet([]), String(sheetData.name ?? sheetId));
      continue;
    }

    const rowIndices = Object.keys(cellData).map(Number).sort((a, b) => a - b);
    const maxRow = rowIndices.length > 0 ? rowIndices[rowIndices.length - 1] + 1 : 0;
    let maxCol = 0;

    for (const ri of rowIndices) {
      const row = cellData[ri];
      if (!row) continue;
      const colIndices = Object.keys(row).map(Number);
      for (const ci of colIndices) {
        if (ci >= maxCol) maxCol = ci + 1;
      }
    }

    const aoa: unknown[][] = [];
    for (let r = 0; r < maxRow; r++) {
      const rowArr: unknown[] = [];
      const rowData = cellData[r];
      for (let c = 0; c < maxCol; c++) {
        rowArr.push(rowData?.[c]?.v ?? '');
      }
      aoa.push(rowArr);
    }

    const ws = XLSX.utils.aoa_to_sheet(aoa);
    XLSX.utils.book_append_sheet(xlsxWorkbook, ws, String(sheetData.name ?? sheetId));
  }

  const wbout = XLSX.write(xlsxWorkbook, { bookType: 'xlsx', type: 'array' });
  return new Blob([wbout], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

const SpreadsheetEditor: React.FC<SpreadsheetEditorProps> = memo(({
  previewUrl,
  filename,
  onSave,
  onDirty,
}) => {
  const t = useTranslations('artifacts');
  const containerRef = useRef<HTMLDivElement>(null);
  const univerRef = useRef<UniverAPI | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const dirtyRef = useRef(false);
  const savedTimerRef = useRef<ReturnType<typeof setTimeout>>();

  const markDirty = useCallback(() => {
    if (!dirtyRef.current) {
      dirtyRef.current = true;
      onDirty(true);
    }
  }, [onDirty]);

  useEffect(() => {
    let disposed = false;
    let commandDisposable: IDisposable | null = null;

    const init = async () => {
      if (!containerRef.current) return;
      setLoading(true);
      setError(null);

      try {
        const url = getStorageUrl(previewUrl);
        const res = await fetch(url);
        if (!res.ok) throw new Error(`Failed to fetch: ${res.status}`);
        const buffer = await res.arrayBuffer();

        if (disposed) return;

        const workbookData = await xlsxToUniverData(buffer);

        const [{ createUniver, LocaleType, mergeLocales }, { UniverSheetsCorePreset }] =
          await Promise.all([
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

        if (disposed || !containerRef.current) return;

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

        univerAPI.createWorkbook(workbookData);
        univerRef.current = univerAPI;

        commandDisposable = univerAPI.onCommandExecuted(() => {
          if (!disposed) markDirty();
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
    if (!api || saving) return;

    const workbook = api.getActiveWorkbook();
    if (!workbook) return;

    setSaving(true);
    setSaved(false);
    setSaveError(false);

    try {
      const snapshot = workbook.save();
      const blob = await univerDataToXlsx(snapshot as WorkbookSnapshot);
      await onSave(blob);
      dirtyRef.current = false;
      onDirty(false);
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
    if (!dirtyRef.current) return;
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  });

  useEffect(() => {
    return () => clearTimeout(savedTimerRef.current);
  }, []);

  if (error) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 p-4">
        <p className="text-sm text-destructive">{t('spreadsheet.loadError')} {filename}</p>
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
