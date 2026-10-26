'use client';

/**
 * [INPUT]
 * - services/system::systemService.getTelemetryPosture (POS: measured OpenTelemetry export posture)
 * - lib/utils/relativeTime::formatRelativeTime (POS: locale-aware "x minutes ago")
 * - components/features/icons/PremiumIcons (POS: Premium SVG icon set)
 *
 * [OUTPUT]
 * - TelemetryPostureCard: Developer-settings card for OTLP trace and metric export: what is configured,
 *   what the exporter actually delivered, and what is never sent
 *
 * [POS]
 * Every value is read from the running exporter (counters, sampler, content switch), never asserted by the UI.
 */

import { memo, useCallback, useEffect, useState, type ReactNode } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { formatRelativeTime } from '@/lib/utils/relativeTime';
import { Button } from '@/components/primitives/button';
import {
  IconActivity,
  IconAlertCircle,
  IconAlertTriangle,
  IconCheck,
  IconCopy,
  IconEye,
  IconGitBranch,
  IconRefresh,
  IconShieldCheck,
} from '@/components/features/icons/PremiumIcons';
import { systemService, type TelemetryPosture } from '@/services/system';

type Tone = 'ok' | 'warn' | 'danger' | 'idle';

const TONE_CLASSES: Record<Tone, { badge: string; dot: string; notice: string; icon: string }> = {
  ok: {
    badge: 'border-primary/30 bg-primary/10 text-primary',
    dot: 'bg-primary',
    notice: 'border-primary/25 bg-primary/5',
    icon: 'text-primary',
  },
  warn: {
    badge: 'border-warning/40 bg-warning/10 text-warning',
    dot: 'bg-warning',
    notice: 'border-warning/35 bg-warning/10',
    icon: 'text-warning',
  },
  danger: {
    badge: 'border-destructive/30 bg-destructive/10 text-destructive dark:text-red-400',
    dot: 'bg-destructive dark:bg-red-400',
    notice: 'border-destructive/30 bg-destructive/5',
    icon: 'text-destructive dark:text-red-400',
  },
  idle: {
    badge: 'border-border bg-muted text-muted-foreground',
    dot: 'bg-muted-foreground/60',
    notice: 'border-border/60 bg-muted/40',
    icon: 'text-muted-foreground',
  },
};

type StatusView = { tone: Tone; labelKey: string; noticeKey: string | null };

const STATUS_VIEW: Record<TelemetryPosture['status'], StatusView> = {
  ready: { tone: 'idle', labelKey: 'ready', noticeKey: 'ready' },
  active: { tone: 'ok', labelKey: 'active', noticeKey: null },
  failing: { tone: 'danger', labelKey: 'failing', noticeKey: 'failing' },
  degraded: { tone: 'warn', labelKey: 'degraded', noticeKey: 'degraded' },
  disabled: { tone: 'idle', labelKey: 'disabled', noticeKey: 'disabled' },
  noop: { tone: 'idle', labelKey: 'noop', noticeKey: 'noop' },
  missing_sdk: { tone: 'warn', labelKey: 'missingSdk', noticeKey: 'missingSdk' },
  local_only: { tone: 'idle', labelKey: 'localOnly', noticeKey: 'localOnly' },
  error: { tone: 'danger', labelKey: 'error', noticeKey: 'error' },
};

const UNREADABLE_POSTURE: TelemetryPosture = {
  status: 'error',
  initialized: false,
  has_sdk: false,
  endpoint: null,
  protocol: 'unknown',
  headers_configured: false,
  local_trace_only: false,
  exporter_type: 'none',
  degraded_reason: null,
  sampler: null,
  content_capture: false,
  metrics_exporting: false,
  exported_spans: 0,
  failed_batches: 0,
  withheld_spans: 0,
  last_success_at: null,
  last_failure_at: null,
  git_branch: null,
  git_commit: null,
};

const ENV_EXAMPLE = [
  '# OpenTelemetry export (standard variables)',
  'OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318"',
  'OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"',
  'OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer your-api-token"',
  'OTEL_TRACES_SAMPLER="parentbased_traceidratio"',
  'OTEL_TRACES_SAMPLER_ARG="0.1"',
].join('\n');

function Field({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={cn('min-w-0 rounded-lg border border-border/40 bg-muted/30 p-2.5', className)}>
      <span className="mb-1 block text-[11px] font-medium tracking-wide text-muted-foreground">{label}</span>
      <div className="min-w-0 text-xs font-medium text-foreground">{children}</div>
    </div>
  );
}

function Counter({ label, value, tone }: { label: string; value: number; tone?: 'warn' | 'danger' }) {
  return (
    <div className="flex min-w-0 items-baseline justify-between gap-3 sm:flex-col-reverse sm:items-start sm:justify-end sm:gap-0.5">
      <span className="min-w-0 break-words text-[11px] leading-tight text-muted-foreground">{label}</span>
      <span
        className={cn(
          'font-mono text-base font-semibold tabular-nums',
          value > 0 && tone === 'danger' && 'text-destructive dark:text-red-400',
          value > 0 && tone === 'warn' && 'text-warning',
        )}
      >
        {value.toLocaleString()}
      </span>
    </div>
  );
}

function PostureBody({ posture, view }: { posture: TelemetryPosture; view: StatusView }) {
  const t = useTranslations('settings.developer.telemetry');
  const locale = useLocale();
  const tone = TONE_CLASSES[view.tone];
  const NoticeIcon = view.tone === 'idle' ? IconAlertCircle : IconAlertTriangle;
  const exporting = posture.initialized && posture.exporter_type !== 'none';
  const lastSeen = (seconds: number | null) =>
    seconds === null ? t('never') : formatRelativeTime(new Date(seconds * 1000).toISOString(), locale);

  return (
    <>
      {view.noticeKey && (
        <output
          className={cn('mt-3 flex items-start gap-2 rounded-lg border p-3 text-xs text-foreground', tone.notice)}
        >
          <NoticeIcon className={cn('mt-0.5 h-3.5 w-3.5 shrink-0', tone.icon)} />
          <span className="min-w-0 break-words">
            {t(`notice.${view.noticeKey}`, { reason: posture.degraded_reason ?? posture.error ?? '' })}
          </span>
        </output>
      )}

      <div className="grid grid-cols-2 gap-3 pt-3.5 lg:grid-cols-4">
        <Field label={t('endpoint')} className="col-span-2">
          <span className="block break-all font-mono">{posture.endpoint ?? t('notConfigured')}</span>
        </Field>
        <Field label={t('protocol')}>
          <span className="font-mono">{posture.endpoint ? posture.protocol.toUpperCase() : '-'}</span>
        </Field>
        <Field label={t('sampler')}>
          <span className="block break-all font-mono">{posture.sampler ?? '-'}</span>
        </Field>

        <Field label={t('contentCapture')} className="col-span-2">
          <span className="flex items-center gap-1.5">
            {posture.content_capture ? (
              <>
                <IconEye className="h-3.5 w-3.5 shrink-0 text-warning" />
                <span className="text-warning">{t('contentIncluded')}</span>
              </>
            ) : (
              <>
                <IconShieldCheck className="h-3.5 w-3.5 shrink-0 text-primary" />
                <span>{t('contentMetadataOnly')}</span>
              </>
            )}
          </span>
        </Field>
        <Field label={t('metrics')}>{posture.metrics_exporting ? t('metricsExporting') : t('metricsOff')}</Field>
        <Field label={t('headers')}>{posture.headers_configured ? t('configured') : t('none')}</Field>

        <Field label={t('environment')} className="col-span-2 lg:col-span-4">
          {posture.git_branch ? (
            <div
              className="flex items-center gap-1.5 truncate font-mono"
              title={`${posture.git_branch} (${posture.git_commit ?? 'HEAD'})`}
            >
              <IconGitBranch className="h-3.5 w-3.5 shrink-0 text-primary" />
              <span className="truncate">{posture.git_branch}</span>
              {posture.git_commit && <span className="text-[10px] text-muted-foreground">({posture.git_commit})</span>}
            </div>
          ) : (
            <span className="text-muted-foreground">{t('noVcsTag')}</span>
          )}
        </Field>
      </div>

      {exporting && (
        <div className="mt-3 rounded-lg border border-border/40 bg-muted/20 p-3">
          <span className="mb-2 block text-[11px] font-medium tracking-wide text-muted-foreground">
            {t('delivery')}
          </span>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3 sm:gap-3">
            <Counter label={t('exportedSpans')} value={posture.exported_spans} />
            <Counter label={t('failedBatches')} value={posture.failed_batches} tone="danger" />
            <Counter label={t('withheldSpans')} value={posture.withheld_spans} tone="warn" />
          </div>
          <div className="mt-2.5 flex flex-col gap-1 text-[11px] text-muted-foreground sm:flex-row sm:gap-5">
            <span>
              {t('lastSuccess')}: <span className="text-foreground">{lastSeen(posture.last_success_at)}</span>
            </span>
            <span>
              {t('lastFailure')}: <span className="text-foreground">{lastSeen(posture.last_failure_at)}</span>
            </span>
          </div>
        </div>
      )}
    </>
  );
}

export const TelemetryPostureCard = memo(() => {
  const t = useTranslations('settings.developer.telemetry');
  const [posture, setPosture] = useState<TelemetryPosture | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  const fetchPosture = useCallback(async () => {
    setLoading(true);
    try {
      setPosture(await systemService.getTelemetryPosture());
    } catch {
      setPosture(UNREADABLE_POSTURE);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPosture();
  }, [fetchPosture]);

  const handleCopyEnvExample = async () => {
    try {
      await navigator.clipboard.writeText(ENV_EXAMPLE);
    } catch {
      return;
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // A status this UI cannot interpret is reported as unreadable rather than guessed at.
  const view = posture ? (STATUS_VIEW[posture.status] ?? STATUS_VIEW.error) : null;

  return (
    <div className="rounded-xl border border-border/50 bg-card/60 p-4 backdrop-blur-sm transition-all sm:p-5">
      <div className="flex flex-col gap-3 border-b border-border/40 pb-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="rounded-lg bg-primary/10 p-2 text-primary">
            <IconActivity className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <h3 className="flex flex-wrap items-center gap-2 text-sm font-semibold tracking-tight text-foreground">
              {t('title')}
              {view && (
                <span
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium',
                    TONE_CLASSES[view.tone].badge,
                  )}
                >
                  <span
                    className={cn(
                      'h-1.5 w-1.5 rounded-full',
                      TONE_CLASSES[view.tone].dot,
                      posture?.status === 'active' && 'animate-pulse motion-reduce:animate-none',
                    )}
                  />
                  {t(`status.${view.labelKey}`)}
                </span>
              )}
            </h3>
            <p className="mt-0.5 text-xs text-muted-foreground">{t('description')}</p>
          </div>
        </div>

        <div className="flex items-center gap-2 self-end sm:self-auto">
          <Button
            variant="outline"
            size="sm"
            onClick={fetchPosture}
            disabled={loading}
            className="h-8 gap-1.5 px-2.5 text-xs"
          >
            <IconRefresh className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
            {t('refresh')}
          </Button>
          <Button variant="ghost" size="sm" onClick={handleCopyEnvExample} className="h-8 gap-1.5 px-2.5 text-xs">
            {copied ? <IconCheck className="h-3.5 w-3.5 text-primary" /> : <IconCopy className="h-3.5 w-3.5" />}
            {copied ? t('copied') : t('copyEnv')}
          </Button>
        </div>
      </div>

      {posture && view ? (
        <PostureBody posture={posture} view={view} />
      ) : (
        <div aria-hidden className="mt-3.5 h-28 animate-pulse rounded-lg bg-muted/40 motion-reduce:animate-none" />
      )}
    </div>
  );
});

TelemetryPostureCard.displayName = 'TelemetryPostureCard';
export default TelemetryPostureCard;
