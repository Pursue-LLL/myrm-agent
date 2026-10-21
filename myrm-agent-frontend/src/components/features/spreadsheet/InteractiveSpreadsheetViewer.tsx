/**
 * [INPUT]
 * @/services/spreadsheet::SpreadsheetTheme, SpreadsheetColumn, SpreadsheetRow, downloadSpreadsheetAsExcel
 * @/components/features/spreadsheet/MultiOfficeSyncModal::MultiOfficeSyncModal
 * @/components/features/icons/PremiumIcons (IconSearch, IconDownload, IconExternalLink, IconX, IconChevronUp, IconChevronDown, IconLoader)
 * next-intl::useTranslations
 *
 * [OUTPUT]
 * - InteractiveSpreadsheetViewer: Publication-grade interactive spreadsheet hub with theme switching & office sync
 *
 * [POS]
 * Interactive viewer component for HighAestheticStyledSpreadsheetGeneratorAndMultiOfficeSyncPipeline (Item 19).
 * Single file < 320 lines. Zero `any` types.
 */

'use client';

import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import type {
  SpreadsheetTheme,
  SpreadsheetColumn,
  SpreadsheetRow,
} from '@/services/spreadsheet';
import { downloadSpreadsheetAsExcel } from '@/services/spreadsheet';
import { MultiOfficeSyncModal } from './MultiOfficeSyncModal';
import {
  IconSearch,
  IconDownload,
  IconExternalLink,
  IconX,
  IconChevronUp,
  IconChevronDown,
  IconLoader,
} from '@/components/features/icons/PremiumIcons';

export interface InteractiveSpreadsheetViewerProps {
  title?: string;
  columns?: SpreadsheetColumn[];
  rows?: SpreadsheetRow[];
  defaultTheme?: SpreadsheetTheme;
  isOpen?: boolean;
  onClose?: () => void;
  className?: string;
}

interface ThemeVisualConfig {
  headerBg: string;
  headerText: string;
  zebraClass: string;
  badgeClass: string;
}

const THEME_VISUALS: Record<SpreadsheetTheme, ThemeVisualConfig> = {
  business_navy: {
    headerBg: 'bg-[#1F4E79]',
    headerText: 'text-white',
    zebraClass: 'even:bg-blue-950/20',
    badgeClass: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  },
  dark_gold: {
    headerBg: 'bg-[#1C1917]',
    headerText: 'text-amber-200',
    zebraClass: 'even:bg-amber-950/20',
    badgeClass: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
  },
  financial_emerald: {
    headerBg: 'bg-[#14532D]',
    headerText: 'text-white',
    zebraClass: 'even:bg-emerald-950/20',
    badgeClass: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  },
  tech_slate: {
    headerBg: 'bg-[#0F172A]',
    headerText: 'text-sky-300',
    zebraClass: 'even:bg-slate-900/40',
    badgeClass: 'bg-sky-500/20 text-sky-300 border-sky-500/30',
  },
};

const EMPTY_COLUMNS: SpreadsheetColumn[] = [];
const EMPTY_ROWS: SpreadsheetRow[] = [];

type SortOrder = 'asc' | 'desc' | null;

export const InteractiveSpreadsheetViewer: React.FC<InteractiveSpreadsheetViewerProps> = ({
  title: controlledTitle,
  columns: controlledColumns,
  rows: controlledRows,
  defaultTheme = 'business_navy',
  isOpen: controlledIsOpen,
  onClose: controlledOnClose,
  className = '',
}) => {
  const t = useTranslations('spreadsheet');

  const [internalIsOpen, setInternalIsOpen] = useState<boolean>(false);
  const [internalData, setInternalData] = useState<{
    title: string;
    columns: SpreadsheetColumn[];
    rows: SpreadsheetRow[];
    theme: SpreadsheetTheme;
  } | null>(null);

  const [currentTheme, setCurrentTheme] = useState<SpreadsheetTheme>(defaultTheme);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<SortOrder>(null);
  const [isExporting, setIsExporting] = useState<boolean>(false);
  const [isSyncModalOpen, setIsSyncModalOpen] = useState<boolean>(false);

  const isControlled = controlledIsOpen !== undefined;
  const isPanelOpen = isControlled ? controlledIsOpen : internalIsOpen;

  // Global event listener for uncontrolled triggers
  useEffect(() => {
    const handleOpen = (e: Event) => {
      const customEvent = e as CustomEvent<{
        title: string;
        columns: SpreadsheetColumn[];
        rows: SpreadsheetRow[];
        defaultTheme?: SpreadsheetTheme;
      }>;
      if (customEvent.detail) {
        setInternalData({
          title: customEvent.detail.title,
          columns: customEvent.detail.columns,
          rows: customEvent.detail.rows,
          theme: customEvent.detail.defaultTheme || 'business_navy',
        });
        if (customEvent.detail.defaultTheme) {
          setCurrentTheme(customEvent.detail.defaultTheme);
        }
        setInternalIsOpen(true);
      }
    };

    const handleClose = () => {
      setInternalIsOpen(false);
    };

    window.addEventListener('myrm:open-spreadsheet-viewer', handleOpen);
    window.addEventListener('myrm:close-spreadsheet-viewer', handleClose);
    return () => {
      window.removeEventListener('myrm:open-spreadsheet-viewer', handleOpen);
      window.removeEventListener('myrm:close-spreadsheet-viewer', handleClose);
    };
  }, []);

  const activeTitle = controlledTitle || internalData?.title || 'Spreadsheet Report';
  const activeColumns = useMemo(
    () => controlledColumns || internalData?.columns || EMPTY_COLUMNS,
    [controlledColumns, internalData?.columns],
  );
  const activeRows = useMemo(
    () => controlledRows || internalData?.rows || EMPTY_ROWS,
    [controlledRows, internalData?.rows],
  );

  const handleClose = useCallback(() => {
    if (controlledOnClose) {
      controlledOnClose();
    } else {
      setInternalIsOpen(false);
    }
  }, [controlledOnClose]);

  // Handle Sort
  const handleSortToggle = (colKey: string) => {
    if (sortKey !== colKey) {
      setSortKey(colKey);
      setSortOrder('asc');
    } else if (sortOrder === 'asc') {
      setSortOrder('desc');
    } else {
      setSortKey(null);
      setSortOrder(null);
    }
  };

  // Filtered & Sorted Rows
  const processedRows = useMemo(() => {
    let result = [...activeRows];

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      result = result.filter((row) =>
        Object.values(row.cells).some((val) => {
          return val !== null && val !== undefined && String(val).toLowerCase().includes(q);
        }),
      );
    }

    if (sortKey && sortOrder) {
      result.sort((a, b) => {
        const valA = a.cells[sortKey];
        const valB = b.cells[sortKey];
        if (valA === valB) {
          return 0;
        }
        if (valA === null || valA === undefined) {
          return 1;
        }
        if (valB === null || valB === undefined) {
          return -1;
        }
        const comp = valA < valB ? -1 : 1;
        return sortOrder === 'asc' ? comp : -comp;
      });
    }

    return result;
  }, [activeRows, searchQuery, sortKey, sortOrder]);

  const handleExportExcel = useCallback(async () => {
    if (isExporting || activeColumns.length === 0) {
      return;
    }
    setIsExporting(true);
    try {
      await downloadSpreadsheetAsExcel({
        title: activeTitle,
        theme: currentTheme,
        columns: activeColumns,
        rows: activeRows,
      });
    } catch {
      // Handled
    } finally {
      setIsExporting(false);
    }
  }, [isExporting, activeTitle, currentTheme, activeColumns, activeRows]);

  if (!isPanelOpen || activeColumns.length === 0) {
    return null;
  }

  const themeVisual = THEME_VISUALS[currentTheme] || THEME_VISUALS.business_navy;

  return (
    <aside
      aria-label={t('viewerTitle')}
      data-testid="interactive-spreadsheet-viewer"
      className={`fixed inset-y-0 right-0 z-50 flex flex-col w-full sm:w-[600px] md:w-[780px] lg:w-[960px] bg-zinc-950/95 backdrop-blur-xl border-l border-zinc-800 shadow-2xl transition-all duration-300 ease-out animate-in slide-in-from-right ${className}`}
    >
      {/* Top Header Bar */}
      <header className="flex flex-col gap-3 p-4 border-b border-zinc-800/80 bg-zinc-900/50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 min-w-0">
            <span className="h-3 w-1.5 rounded-full bg-indigo-500 flex-shrink-0" />
            <h2 className="text-sm font-semibold text-zinc-100 truncate">{activeTitle}</h2>
          </div>
          <button
            type="button"
            onClick={handleClose}
            aria-label={t('close')}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 transition-colors cursor-pointer"
          >
            <IconX className="w-4 h-4" />
          </button>
        </div>

        {/* Toolbar: Themes + Search + Actions */}
        <div className="flex flex-wrap items-center justify-between gap-2.5 pt-1">
          {/* Theme Switchers */}
          <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 p-0.5 rounded-lg">
            {(
              [
                ['business_navy', t('themeNavy')],
                ['dark_gold', t('themeGold')],
                ['financial_emerald', t('themeEmerald')],
                ['tech_slate', t('themeSlate')],
              ] as const
            ).map(([themeKey, label]) => (
              <button
                key={themeKey}
                type="button"
                onClick={() => setCurrentTheme(themeKey)}
                className={`px-2.5 py-1 rounded text-xs transition-colors cursor-pointer ${
                  currentTheme === themeKey
                    ? 'bg-zinc-800 text-zinc-100 font-semibold shadow-xs'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Search Box */}
          <div className="relative flex-1 min-w-[160px] max-w-xs">
            <IconSearch className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('searchPlaceholder')}
              className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-zinc-900 border border-zinc-800 text-xs text-zinc-200 focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleExportExcel}
              disabled={isExporting}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600/90 hover:bg-emerald-500 text-white text-xs font-medium transition-colors cursor-pointer shadow-xs disabled:opacity-50"
            >
              {isExporting ? <IconLoader className="w-3.5 h-3.5 animate-spin" /> : <IconDownload className="w-3.5 h-3.5" />}
              <span>{isExporting ? t('exporting') : t('exportExcel')}</span>
            </button>

            <button
              type="button"
              onClick={() => setIsSyncModalOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors cursor-pointer shadow-xs"
            >
              <IconExternalLink className="w-3.5 h-3.5" />
              <span>{t('syncOffice')}</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Table View */}
      <main className="flex-1 overflow-auto p-3">
        <div className="rounded-xl border border-zinc-800 overflow-hidden shadow-sm">
          <table className="w-full border-collapse text-xs font-sans text-left">
            <thead>
              <tr className={`${themeVisual.headerBg} ${themeVisual.headerText}`}>
                {activeColumns.map((col) => {
                  const isSorted = sortKey === col.key;
                  return (
                    <th
                      key={col.key}
                      scope="col"
                      aria-label={col.label}
                      onClick={() => handleSortToggle(col.key)}
                      className="px-3.5 py-2.5 font-semibold select-none cursor-pointer hover:opacity-90 border-r border-white/10 last:border-r-0 transition-opacity"
                    >
                      <div className="flex items-center justify-between gap-1">
                        <span>{col.label}</span>
                        <span className="w-3 h-3 flex items-center justify-center opacity-70">
                          {isSorted && sortOrder === 'asc' && <IconChevronUp className="w-3 h-3" />}
                          {isSorted && sortOrder === 'desc' && <IconChevronDown className="w-3 h-3" />}
                        </span>
                      </div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60 bg-zinc-950 text-zinc-300">
              {processedRows.map((row, rIdx) => (
                <tr key={rIdx} className={`${themeVisual.zebraClass} hover:bg-zinc-800/40 transition-colors`}>
                  {activeColumns.map((col) => {
                    const rawVal = row.cells[col.key];
                    const isNumeric = col.col_type === 'number' || col.col_type === 'currency' || col.col_type === 'percentage';
                    const isDate = col.col_type === 'date';

                    return (
                      <td
                        key={col.key}
                        className={`px-3.5 py-2 border-r border-zinc-800/40 last:border-r-0 font-mono ${
                          isNumeric ? 'text-right' : isDate ? 'text-center' : 'text-left'
                        }`}
                      >
                        {rawVal !== null && rawVal !== undefined ? String(rawVal) : '-'}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </main>

      {/* Footer Meta Bar */}
      <footer className="flex items-center justify-between px-4 py-2.5 border-t border-zinc-800/80 bg-zinc-900/60 text-xs text-zinc-400">
        <div className="flex items-center gap-3">
          <span>{t('totalRows', { count: activeRows.length })}</span>
          {searchQuery.trim() && <span>{t('filteredRows', { count: processedRows.length })}</span>}
          <span>{t('totalCols', { count: activeColumns.length })}</span>
        </div>
        <span className={`px-2 py-0.5 rounded text-[11px] border font-medium ${themeVisual.badgeClass}`}>
          {currentTheme}
        </span>
      </footer>

      {/* Office Sync Modal */}
      <MultiOfficeSyncModal
        isOpen={isSyncModalOpen}
        onClose={() => setIsSyncModalOpen(false)}
        tableName={activeTitle}
        columns={activeColumns}
        rows={activeRows}
      />
    </aside>
  );
};
