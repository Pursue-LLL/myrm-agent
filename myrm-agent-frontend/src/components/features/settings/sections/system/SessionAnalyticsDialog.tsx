'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconX, IconAlertCircle, IconCopy, IconCheck, IconDownload } from '@/components/features/icons/PremiumIcons';
import { getSessionAnalytics, type SessionAnalytics } from '@/services/statistics';
import { cn } from '@/lib/utils/classnameUtils';
import SessionContextHealthPanel from './SessionContextHealthPanel';
import ExecutionTraceTimeline from './ExecutionTraceTimeline';
import ContextBreakdownCard from './ContextBreakdownCard';
import {
  EventsTimelineSection,
  LlmBreakdownSection,
  ResponseSpeedSection,
  SecurityAuditSection,
  SessionStatCards,
  TokenEconomicsSection,
  ToolBreakdownSection,
} from './SessionAnalyticsSections';
import { buildAuditCsv, buildAuditMarkdown, copyTextToClipboard, downloadCsvFile } from './sessionAuditExport';

interface SessionAnalyticsDialogProps {
  sessionId: string;
  onClose: () => void;
}

const SessionAnalyticsDialog = memo<SessionAnalyticsDialogProps>(({ sessionId, onClose }) => {
  const t = useTranslations('settings.sessionAnalytics');
  const tm = useTranslations('mode');
  const [data, setData] = useState<SessionAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleCopyMarkdown = useCallback(async () => {
    if (!data) {
      return;
    }
    if (await copyTextToClipboard(buildAuditMarkdown(data))) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [data]);

  const handleDownloadCsv = useCallback(() => {
    if (!data) {
      return;
    }
    downloadCsvFile(`audit-ledger-${data.session_id.slice(0, 8)}.csv`, buildAuditCsv(data));
  }, [data]);

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        setError(null);
        const result = await getSessionAnalytics(sessionId, true);
        setData(result);
      } catch (err) {
        if (err instanceof Error) {
          const message = err.message.toLowerCase();
          if (message.includes('not found') || message.includes('404')) {
            setError(t('sessionNotFound'));
          } else if (message.includes('access denied') || message.includes('403') || message.includes('forbidden')) {
            setError(t('accessDenied'));
          } else if (message.includes('500') || message.includes('internal')) {
            setError(t('serverError'));
          } else {
            setError(err.message);
          }
        } else {
          setError(t('loadFailed'));
        }
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [sessionId, t]);

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) {
        onClose();
      }
    },
    [onClose],
  );

  if (loading) {
    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
        role="presentation"
        onClick={handleBackdropClick}
      >
        <div className="bg-background border border-border rounded-lg p-8 max-w-4xl w-full mx-4">
          <div className="flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
          </div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
        role="presentation"
        onClick={handleBackdropClick}
      >
        <div className="bg-background border border-border rounded-lg p-8 max-w-4xl w-full mx-4">
          <div className="flex items-center gap-2 text-destructive-text">
            <IconAlertCircle className="w-5 h-5" />
            <span>{error || t('sessionNotFound')}</span>
          </div>
          <button
            onClick={onClose}
            className="mt-4 px-4 py-2 bg-primary text-primary-foreground rounded-full hover:bg-primary/90"
          >
            {t('close')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      role="presentation"
      onClick={handleBackdropClick}
    >
      <div className="bg-background border border-border rounded-lg max-w-4xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-background border-b border-border p-6 flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <h2 className="text-xl font-bold text-foreground truncate">{data.title || t('untitledSession')}</h2>
            <p className="text-sm text-muted-foreground mt-1">
              {tm.has(data.action_mode) ? tm(data.action_mode) : data.action_mode} •{' '}
              {data.created_at ? new Date(data.created_at).toLocaleString() : 'N/A'}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={handleCopyMarkdown}
              className={cn(
                'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-all border',
                copied
                  ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30'
                  : 'bg-muted/60 text-muted-foreground hover:text-foreground hover:bg-muted border-border/60',
              )}
              title={t('copyMarkdownTooltip')}
              aria-label={t('copyMarkdown')}
            >
              {copied ? (
                <IconCheck className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
              ) : (
                <IconCopy className="w-3.5 h-3.5 shrink-0" />
              )}
              <span className="hidden sm:inline">{copied ? t('copied') : t('copyMarkdown')}</span>
            </button>
            <button
              onClick={handleDownloadCsv}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-all border bg-muted/60 text-muted-foreground hover:text-foreground hover:bg-muted border-border/60"
              title={t('downloadCsvTooltip')}
              aria-label={t('downloadCsv')}
            >
              <IconDownload className="w-3.5 h-3.5 shrink-0" />
              <span className="hidden sm:inline">{t('downloadCsv')}</span>
            </button>
            <button
              onClick={onClose}
              className="p-1.5 hover:bg-muted rounded-full transition-colors text-muted-foreground hover:text-foreground"
              aria-label={t('close')}
            >
              <IconX className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="p-6 space-y-6">
          {/* Stat Cards */}
          <SessionStatCards data={data} />

          <SessionContextHealthPanel health={data.context_health} sessionId={sessionId} />

          <TokenEconomicsSection data={data} />

          <ResponseSpeedSection data={data} />

          {/* Context Doctor Breakdown */}
          {data.context_breakdown && <ContextBreakdownCard breakdown={data.context_breakdown} />}

          <ExecutionTraceTimeline sessionId={sessionId} />

          <LlmBreakdownSection data={data} />

          <ToolBreakdownSection data={data} />

          <SecurityAuditSection data={data} />

          <EventsTimelineSection data={data} />
        </div>
      </div>
    </div>
  );
});
SessionAnalyticsDialog.displayName = 'SessionAnalyticsDialog';

export default SessionAnalyticsDialog;
