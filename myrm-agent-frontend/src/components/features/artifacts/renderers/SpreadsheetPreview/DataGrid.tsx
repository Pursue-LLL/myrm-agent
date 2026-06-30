'use client';

import React, { memo, useCallback, useDeferredValue, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useVirtualizer } from '@tanstack/react-virtual';
import { cn } from '@/lib/utils/classnameUtils';

interface DataGridProps {
  headers: string[];
  rows: string[][];
  totalRows?: number;
  className?: string;
}

type SortDir = 'asc' | 'desc' | null;

const ROW_HEIGHT = 32;

function columnLabel(index: number): string {
  let label = '';
  let n = index;
  do {
    label = String.fromCharCode(65 + (n % 26)) + label;
    n = Math.floor(n / 26) - 1;
  } while (n >= 0);
  return label;
}

function isNumeric(value: string): boolean {
  if (value === '') return false;
  const cleaned = value.replace(/[$€¥£,\s%]/g, '');
  return !isNaN(Number(cleaned)) && cleaned.length > 0;
}

function detectNumericColumns(headers: string[], rows: string[][]): boolean[] {
  const sampleSize = Math.min(rows.length, 50);
  return headers.map((_, colIdx) => {
    let numericCount = 0;
    let nonEmptyCount = 0;
    for (let i = 0; i < sampleSize; i++) {
      const val = rows[i]?.[colIdx] ?? '';
      if (val.trim() === '') continue;
      nonEmptyCount++;
      if (isNumeric(val)) numericCount++;
    }
    return nonEmptyCount > 0 && numericCount / nonEmptyCount > 0.7;
  });
}

function compareValues(a: string, b: string, numeric: boolean): number {
  if (numeric) {
    const na = parseFloat(a.replace(/[$€¥£,\s%]/g, '')) || 0;
    const nb = parseFloat(b.replace(/[$€¥£,\s%]/g, '')) || 0;
    return na - nb;
  }
  return a.localeCompare(b);
}

const DataGrid: React.FC<DataGridProps> = memo(({ headers, rows, totalRows, className }) => {
  const t = useTranslations('artifacts.spreadsheet');
  const parentRef = useRef<HTMLDivElement>(null);
  const [sortCol, setSortCol] = useState<number | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>(null);
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search);
  const [selectedRow, setSelectedRow] = useState<number | null>(null);

  const numericCols = useMemo(() => detectNumericColumns(headers, rows), [headers, rows]);

  const filteredRows = useMemo(() => {
    if (!deferredSearch.trim()) return rows;
    const q = deferredSearch.toLowerCase();
    return rows.filter((row) => row.some((cell) => cell.toLowerCase().includes(q)));
  }, [rows, deferredSearch]);

  const sortedRows = useMemo(() => {
    if (sortCol === null || sortDir === null) return filteredRows;
    const isNum = numericCols[sortCol];
    const sorted = [...filteredRows].sort((a, b) => compareValues(a[sortCol], b[sortCol], isNum));
    return sortDir === 'desc' ? sorted.reverse() : sorted;
  }, [filteredRows, sortCol, sortDir, numericCols]);

  const virtualizer = useVirtualizer({
    count: sortedRows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 20,
  });

  const handleSort = useCallback(
    (colIdx: number) => {
      if (sortCol === colIdx) {
        if (sortDir === 'asc') setSortDir('desc');
        else if (sortDir === 'desc') {
          setSortCol(null);
          setSortDir(null);
        }
      } else {
        setSortCol(colIdx);
        setSortDir('asc');
      }
    },
    [sortCol, sortDir],
  );

  const handleCopy = useCallback(() => {
    const headerLine = headers.join('\t');
    const dataLines = sortedRows.map((r) => r.join('\t')).join('\n');
    navigator.clipboard.writeText(`${headerLine}\n${dataLines}`).catch(() => {});
  }, [headers, sortedRows]);

  const handleExport = useCallback(() => {
    const escapeCell = (cell: string) => {
      if (cell.includes(',') || cell.includes('"') || cell.includes('\n')) {
        return `"${cell.replace(/"/g, '""')}"`;
      }
      return cell;
    };
    const headerLine = headers.map(escapeCell).join(',');
    const dataLines = sortedRows
      .map((r) => r.map(escapeCell).join(','))
      .join('\n');
    const blob = new Blob([`${headerLine}\n${dataLines}`], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'export.csv';
    a.click();
    URL.revokeObjectURL(url);
  }, [headers, sortedRows]);

  const showTruncated = totalRows != null && totalRows > rows.length;
  const showFiltered = deferredSearch.trim() && sortedRows.length !== rows.length;

  return (
    <div className={cn('flex flex-col h-full bg-background', className)}>
      {/* Toolbar */}
      <div className="shrink-0 flex flex-wrap items-center gap-1.5 sm:gap-2 px-2 sm:px-3 py-1.5 border-b border-border bg-muted/30">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t('search')}
          className="flex-1 min-w-[100px] h-7 px-2 text-xs rounded border border-border bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
        />
        <span className="text-[11px] text-muted-foreground whitespace-nowrap">
          {showFiltered && `${sortedRows.length} / `}
          {rows.length}
          {showTruncated && ` ${t('of')} ${totalRows!.toLocaleString()}`} {t('rows')}
        </span>
        <button
          onClick={handleCopy}
          className="h-7 px-2 text-[11px] rounded border border-border bg-background text-foreground hover:bg-muted transition-colors"
          title={t('copyAll')}
        >
          {t('copy')}
        </button>
        <button
          onClick={handleExport}
          className="h-7 px-2 text-[11px] rounded border border-border bg-background text-foreground hover:bg-muted transition-colors"
          title={t('exportCsv')}
        >
          {t('export')}
        </button>
      </div>

      {/* Table */}
      <div ref={parentRef} className="flex-1 min-h-0 overflow-auto">
        <div style={{ height: `${virtualizer.getTotalSize() + ROW_HEIGHT}px`, position: 'relative' }}>
          {/* Sticky header */}
          <div className="sticky top-0 z-10 flex bg-muted border-b border-border" style={{ height: ROW_HEIGHT }}>
            {headers.map((h, i) => (
              <div
                key={i}
                onClick={() => handleSort(i)}
                className={cn(
                  'flex items-center px-3 text-[11px] font-semibold text-foreground cursor-pointer select-none whitespace-nowrap',
                  'border-r border-border last:border-r-0 hover:bg-muted/80 transition-colors',
                  numericCols[i] && 'justify-end',
                )}
                style={{ minWidth: 72, maxWidth: 320, flex: '1 0 auto' }}
              >
                <span className="truncate">{h || columnLabel(i)}</span>
                {sortCol === i && (
                  <span className="ml-1 text-primary">{sortDir === 'asc' ? '↑' : '↓'}</span>
                )}
              </div>
            ))}
          </div>

          {/* Virtual rows */}
          {virtualizer.getVirtualItems().map((vRow) => {
            const row = sortedRows[vRow.index];
            const isSelected = selectedRow === vRow.index;
            return (
              <div
                key={vRow.index}
                onClick={() => setSelectedRow(isSelected ? null : vRow.index)}
                className={cn(
                  'absolute left-0 right-0 flex cursor-pointer transition-colors',
                  isSelected
                    ? 'bg-primary/10'
                    : vRow.index % 2 === 0
                      ? 'bg-background hover:bg-muted/40'
                      : 'bg-muted/20 hover:bg-muted/40',
                )}
                style={{
                  height: ROW_HEIGHT,
                  top: vRow.start + ROW_HEIGHT,
                }}
              >
                {headers.map((_, ci) => {
                  const val = row?.[ci] ?? '';
                  const isEmpty = val.trim() === '';
                  return (
                    <div
                      key={ci}
                      className={cn(
                        'flex items-center px-3 text-[12px] border-r border-border/50 last:border-r-0 whitespace-nowrap',
                        numericCols[ci] ? 'justify-end font-mono' : 'text-foreground',
                        isEmpty && 'text-muted-foreground/40',
                      )}
                      style={{ minWidth: 72, maxWidth: 320, flex: '1 0 auto' }}
                      title={val}
                    >
                      <span className="truncate">{isEmpty ? '—' : val}</span>
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
});

DataGrid.displayName = 'DataGrid';
export default DataGrid;
