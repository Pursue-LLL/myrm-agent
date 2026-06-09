'use client';

import React, { memo, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { parseCsv } from './CsvParser';
import DataGrid from './DataGrid';
import { getStorageUrl } from '@/lib/api';

interface SpreadsheetPreviewProps {
  content: string;
  filename: string;
  previewUrl?: string;
}

const MAX_ROWS = 10_000;

interface SheetData {
  name: string;
  headers: string[];
  rows: string[][];
  totalRows: number;
}

const XlsxViewer: React.FC<{ url: string; filename: string }> = memo(({ url, filename }) => {
  const t = useTranslations('artifacts.spreadsheet');
  const [sheets, setSheets] = useState<SheetData[]>([]);
  const [activeSheet, setActiveSheet] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`Failed to fetch: ${res.status}`);
        const buffer = await res.arrayBuffer();
        const XLSX = await import('xlsx');
        const workbook = XLSX.read(new Uint8Array(buffer), { type: 'array' });

        if (cancelled) return;

        const parsed = workbook.SheetNames.map((name) => {
          const sheet = workbook.Sheets[name];
          const json = XLSX.utils.sheet_to_json<string[]>(sheet, { header: 1, defval: '' });
          const allRows = json as string[][];
          const headers = allRows[0]?.map(String) ?? [];
          const dataRows = allRows.slice(1).map((row) => row.map(String));
          const totalRows = dataRows.length;
          const rows = dataRows.slice(0, MAX_ROWS);
          return { name, headers, rows, totalRows };
        });

        setSheets(parsed);
        setActiveSheet(0);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [url]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-2 border-muted-foreground/30 border-t-primary rounded-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-2 p-4">
        <p className="text-sm text-destructive">{t('loadError')} {filename}</p>
        <p className="text-xs text-muted-foreground">{error}</p>
      </div>
    );
  }

  const current = sheets[activeSheet];
  if (!current) return null;

  return (
    <div className="flex flex-col h-full">
      {sheets.length > 1 && (
        <div className="shrink-0 flex gap-0 border-b border-border overflow-x-auto bg-muted/50">
          {sheets.map((s, i) => (
            <button
              key={s.name}
              onClick={() => setActiveSheet(i)}
              className={`px-3 py-1.5 text-[11px] border-r border-border whitespace-nowrap transition-colors ${
                i === activeSheet
                  ? 'bg-background text-foreground font-medium'
                  : 'text-muted-foreground hover:bg-muted/80'
              }`}
            >
              {s.name}
            </button>
          ))}
        </div>
      )}
      <div className="flex-1 min-h-0">
        <DataGrid headers={current.headers} rows={current.rows} totalRows={current.totalRows} />
      </div>
    </div>
  );
});
XlsxViewer.displayName = 'XlsxViewer';

const CsvViewer: React.FC<{ content: string }> = memo(({ content }) => {
  const t = useTranslations('artifacts.spreadsheet');
  const parsed = useMemo(() => parseCsv(content, MAX_ROWS), [content]);

  if (parsed.headers.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-sm text-muted-foreground">{t('noData')}</p>
      </div>
    );
  }

  return <DataGrid headers={parsed.headers} rows={parsed.rows} totalRows={parsed.totalRows} />;
});
CsvViewer.displayName = 'CsvViewer';

const SpreadsheetPreview: React.FC<SpreadsheetPreviewProps> = memo(({ content, filename, previewUrl }) => {
  const t = useTranslations('artifacts.spreadsheet');
  const isXlsx = /\.(xlsx|xls)$/i.test(filename);

  if (isXlsx) {
    if (previewUrl) {
      return <XlsxViewer url={getStorageUrl(previewUrl)} filename={filename} />;
    }
    return (
      <div className="h-full flex flex-col items-center justify-center gap-2 p-4">
        <p className="text-sm text-muted-foreground">{t('noData')}</p>
      </div>
    );
  }

  return <CsvViewer content={content} />;
});

SpreadsheetPreview.displayName = 'SpreadsheetPreview';
export default SpreadsheetPreview;
