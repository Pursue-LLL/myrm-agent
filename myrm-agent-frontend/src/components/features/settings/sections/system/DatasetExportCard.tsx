'use client';

import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/lib/utils/toast';
import {
  listExportFormats,
  triggerExport,
  listExportFiles,
  getExportFileDownloadUrl,
  type ExportFormatInfo,
  type ExportReport,
  type ExportFileInfo,
} from '@/services/dataset-export';
import { getApiUrl } from '@/lib/api';
import SettingsSection from '../SettingsSection';

const DatasetExportCard = memo(() => {
  const t = useTranslations('settings');

  const [formats, setFormats] = useState<ExportFormatInfo[]>([]);
  const [selectedFormats, setSelectedFormats] = useState<Set<string>>(new Set(['sharegpt']));
  const [redactPii, setRedactPii] = useState(true);
  const [maxSamples, setMaxSamples] = useState(0);
  const [incremental, setIncremental] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [lastReport, setLastReport] = useState<ExportReport | null>(null);
  const [files, setFiles] = useState<ExportFileInfo[]>([]);

  useEffect(() => {
    listExportFormats()
      .then(setFormats)
      .catch(() => {});
    listExportFiles()
      .then(setFiles)
      .catch(() => {});
  }, []);

  const refreshFiles = useCallback(() => {
    listExportFiles()
      .then(setFiles)
      .catch(() => {});
  }, []);

  const toggleFormat = useCallback((id: string) => {
    setSelectedFormats((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        if (next.size > 1) next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const handleExport = useCallback(async () => {
    if (selectedFormats.size === 0) {
      toast.error(t('datasetExport.selectFormat'));
      return;
    }
    setExporting(true);
    setLastReport(null);
    try {
      const report = await triggerExport({
        formats: Array.from(selectedFormats),
        redact_pii: redactPii,
        max_samples: maxSamples,
        require_success: true,
        min_turns: 2,
        min_content_length: 50,
        incremental,
      });
      setLastReport(report);
      refreshFiles();
      if (report.samples_exported > 0) {
        toast.success(t('datasetExport.exportSuccess', { count: report.samples_exported }));
      } else {
        toast.warning(t('datasetExport.noData'));
      }
    } catch {
      toast.error(t('datasetExport.exportFailed'));
    } finally {
      setExporting(false);
    }
  }, [selectedFormats, redactPii, maxSamples, incremental, t, refreshFiles]);

  const formatBytes = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <SettingsSection title={t('datasetExport.title')} description={t('datasetExport.description')}>
      <div className="space-y-5">
        {/* Format Selection */}
        <div>
          <label className="text-sm font-medium text-foreground mb-2 block">
            {t('datasetExport.formats')}
          </label>
          <div className="flex flex-wrap gap-2">
            {formats.map((fmt) => (
              <button
                key={fmt.id}
                onClick={() => toggleFormat(fmt.id)}
                className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                  selectedFormats.has(fmt.id)
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-secondary/50 text-muted-foreground border-border/50 hover:bg-secondary'
                }`}
                title={fmt.description}
              >
                {fmt.name}
              </button>
            ))}
          </div>
        </div>

        {/* Options */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={redactPii}
              onChange={(e) => setRedactPii(e.target.checked)}
              className="rounded border-border"
            />
            <span className="text-muted-foreground">{t('datasetExport.redactPii')}</span>
          </label>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={incremental}
              onChange={(e) => setIncremental(e.target.checked)}
              className="rounded border-border"
            />
            <span className="text-muted-foreground">{t('datasetExport.incremental')}</span>
          </label>

          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground whitespace-nowrap">
              {t('datasetExport.maxSamples')}
            </span>
            <input
              type="number"
              min={0}
              value={maxSamples}
              onChange={(e) => setMaxSamples(Math.max(0, parseInt(e.target.value) || 0))}
              className="w-20 px-2 py-1 rounded-md border border-border bg-background text-sm"
              placeholder="0"
            />
          </label>
        </div>

        {/* Export Button */}
        <button
          onClick={handleExport}
          disabled={exporting}
          className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {exporting ? t('datasetExport.exporting') : t('datasetExport.exportBtn')}
        </button>

        {/* Report */}
        {lastReport && (
          <div className="rounded-lg border border-border/50 bg-background/50 p-4 text-sm space-y-1">
            <p className="font-medium text-foreground">{t('datasetExport.reportTitle')}</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-muted-foreground">
              <span>
                {t('datasetExport.scanned')}: {lastReport.total_sessions_scanned}
              </span>
              <span>
                {t('datasetExport.passed')}: {lastReport.traces_passed_quality}
              </span>
              <span>
                {t('datasetExport.exported')}: {lastReport.samples_exported}
              </span>
              <span>
                {t('datasetExport.piiRedacted')}: {lastReport.pii_redactions}
              </span>
            </div>
            {lastReport.errors.length > 0 && (
              <p className="text-destructive text-xs mt-1">
                {t('datasetExport.errors')}: {lastReport.errors.join('; ')}
              </p>
            )}
          </div>
        )}

        {/* Existing Files */}
        {files.length > 0 && (
          <div className="space-y-2">
            <p className="text-sm font-medium text-foreground">{t('datasetExport.existingFiles')}</p>
            <div className="space-y-1">
              {files.map((f) => (
                <div
                  key={f.name}
                  className="flex items-center justify-between px-3 py-2 rounded-lg bg-secondary/30 border border-border/30 text-sm"
                >
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-xs text-muted-foreground">{f.format.toUpperCase()}</span>
                    <span className="text-foreground">{f.name}</span>
                    <span className="text-xs text-muted-foreground">
                      {formatBytes(f.size_bytes)} · {f.line_count} {t('datasetExport.samples')}
                    </span>
                  </div>
                  <a
                    href={getApiUrl(getExportFileDownloadUrl(f.name))}
                    download={f.name}
                    className="text-primary hover:underline text-xs"
                  >
                    {t('datasetExport.download')}
                  </a>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </SettingsSection>
  );
});

DatasetExportCard.displayName = 'DatasetExportCard';

export default DatasetExportCard;
