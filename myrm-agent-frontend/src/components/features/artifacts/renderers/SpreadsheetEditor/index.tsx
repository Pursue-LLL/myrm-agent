'use client';

/**
 * [INPUT]
 * `@/lib/api`::getStorageUrl（POS: API URL 拼接工具）；
 * `@univerjs/presets` + `@univerjs/preset-sheets-core`（POS: Univer Sheet 编辑器引擎）；
 * `./dataConversion`（POS: SheetJS XLSX ↔ Univer 数据转换）；
 * `./draftStorage`（POS: IndexedDB 自动草稿持久化与恢复）。
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

import { xlsxToUniverData, univerDataToXlsx, type WorkbookSnapshot, type FidelityWarnings } from './dataConversion';
import { getDraftKey, saveDraft, loadDraft, deleteDraft } from './draftStorage';

type UniverAPI = Awaited<ReturnType<(typeof import('@univerjs/presets'))['createUniver']>>['univerAPI'];

interface SpreadsheetEditorProps {
  previewUrl: string;
  filename: string;
  onSave: (blob: Blob) => Promise<void>;
  onDirty: (dirty: boolean) => void;
}

const DRAFT_AUTO_SAVE_DELAY_MS = 5000;

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

        // Selection, the in-cell editor's document and formula recalculation emit commands too, even right after
        // the workbook opens; only a sheet mutation that would be synced to replicas is an edit.
        commandDisposable = univerAPI.addEvent(univerAPI.Event.CommandExecuted, (event) => {
          if (!disposed && event.id.startsWith('sheet.mutation.') && !event.options?.onlyLocal) {
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
        <p className="text-sm text-destructive-text">
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
            aria-label={t('close')}
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
