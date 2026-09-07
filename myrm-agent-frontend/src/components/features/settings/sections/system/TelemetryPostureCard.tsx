'use client';

/**
 * [INPUT]
 * - services/system::systemService.getTelemetryPosture (POS: SRE OpenTelemetry Posture API)
 * - components/features/icons/PremiumIcons (POS: Premium SVG icon set)
 *
 * [OUTPUT]
 * - TelemetryPostureCard: Diagnostic status card for OpenTelemetry OTLP tracing and APM exporter
 *
 * [POS]
 * Developer settings diagnostics. Surfaces active OpenTelemetry telemetry status, protocol,
 * endpoints, and APM config snippet guides for enterprise SRE.
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import {
  IconActivity,
  IconCheck,
  IconCopy,
  IconGitBranch,
  IconRefresh,
  IconWorkflow,
} from '@/components/features/icons/PremiumIcons';
import { systemService, type TelemetryPosture } from '@/services/system';

const STATUS_MAP = {
  active: {
    badge: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
    dot: 'bg-emerald-500',
    labelKey: 'active',
  },
  console: {
    badge: 'bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/20',
    dot: 'bg-blue-500',
    labelKey: 'console',
  },
  degraded_console: {
    badge: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/20',
    dot: 'bg-amber-500',
    labelKey: 'degradedConsole',
  },
  noop: {
    badge: 'bg-muted text-muted-foreground border-border/40',
    dot: 'bg-muted-foreground/60',
    labelKey: 'noop',
  },
  missing_sdk: {
    badge: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/20',
    dot: 'bg-amber-500',
    labelKey: 'missingSdk',
  },
  local_only: {
    badge: 'bg-purple-500/15 text-purple-600 dark:text-purple-400 border-purple-500/20',
    dot: 'bg-purple-500',
    labelKey: 'localOnly',
  },
  error: {
    badge: 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/20',
    dot: 'bg-rose-500',
    labelKey: 'error',
  },
} as const;

export const TelemetryPostureCard = memo(() => {
  const t = useTranslations('settings.developer.telemetry');
  const [posture, setPosture] = useState<TelemetryPosture | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  const fetchPosture = useCallback(async () => {
    setLoading(true);
    try {
      const data = await systemService.getTelemetryPosture();
      setPosture(data);
    } catch {
      setPosture({
        status: 'error',
        initialized: false,
        has_sdk: false,
        endpoint: null,
        protocol: 'unknown',
        headers_configured: false,
        local_trace_only: false,
        three_tier_semantics: true,
        prompt_cache_metering: true,
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPosture();
  }, [fetchPosture]);

  const handleCopyEnvExample = () => {
    const example = `# OpenTelemetry APM Collector Integration\nOTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318"\nOTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"\nOTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer your-api-token"\nOTEL_SAMPLE_RATE="0.1"`;
    navigator.clipboard.writeText(example);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const statusConfig = posture ? STATUS_MAP[posture.status] || STATUS_MAP.noop : STATUS_MAP.noop;

  return (
    <div className="rounded-xl border border-border/50 bg-card/60 backdrop-blur-sm p-4 sm:p-5 transition-all">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-3 border-b border-border/40">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-primary/10 text-primary">
            <IconActivity className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground tracking-tight flex items-center gap-2">
              {t('title')}
              <span
                className={cn(
                  'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border',
                  statusConfig.badge,
                )}
              >
                <span className={cn('h-1.5 w-1.5 rounded-full animate-pulse', statusConfig.dot)} />
                {t(`status.${statusConfig.labelKey}`)}
              </span>
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">{t('description')}</p>
          </div>
        </div>

        <div className="flex items-center gap-2 self-end sm:self-auto">
          <Button
            variant="outline"
            size="sm"
            onClick={fetchPosture}
            disabled={loading}
            className="h-8 px-2.5 text-xs gap-1.5"
          >
            <IconRefresh className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
            {t('refresh')}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleCopyEnvExample}
            className="h-8 px-2.5 text-xs gap-1.5"
          >
            {copied ? <IconCheck className="h-3.5 w-3.5 text-emerald-500" /> : <IconCopy className="h-3.5 w-3.5" />}
            {copied ? t('copied') : t('copyEnv')}
          </Button>
        </div>
      </div>

      {posture?.status === 'degraded_console' && (
        <div className="mt-3 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-800 dark:text-amber-300">
          <div className="font-semibold flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-amber-500" />
            {t('degradedWarning')}
          </div>
          <div className="mt-1 text-muted-foreground">
            {t('degradedHelp', { reason: posture.degraded_reason || 'Unknown error' })}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 pt-3.5 text-xs">
        <div className="p-2.5 rounded-lg bg-muted/40 border border-border/30">
          <span className="text-muted-foreground block mb-1">{t('protocol')}</span>
          <span className="font-mono font-medium text-foreground">
            {posture?.protocol ? posture.protocol.toUpperCase() : 'NOOP'}
          </span>
        </div>

        <div className="p-2.5 rounded-lg bg-muted/40 border border-border/30">
          <span className="text-muted-foreground block mb-1">{t('endpoint')}</span>
          <span className="font-mono font-medium text-foreground truncate block" title={posture?.endpoint || ''}>
            {posture?.endpoint || t('notConfigured')}
          </span>
        </div>

        <div className="p-2.5 rounded-lg bg-muted/40 border border-border/30">
          <span className="text-muted-foreground block mb-1">{t('environment')}</span>
          {posture?.git_branch ? (
            <div className="flex items-center gap-1.5 font-mono font-medium text-foreground truncate" title={`${posture.git_branch} (${posture.git_commit || 'HEAD'})`}>
              <IconGitBranch className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
              <span className="truncate">{posture.git_branch}</span>
              {posture.git_commit && (
                <span className="text-muted-foreground text-[10px]">({posture.git_commit})</span>
              )}
            </div>
          ) : (
            <span className="font-medium text-muted-foreground">{t('noVcsTag')}</span>
          )}
        </div>

        <div className="p-2.5 rounded-lg bg-muted/40 border border-border/30">
          <span className="text-muted-foreground block mb-1">{t('features')}</span>
          <div className="flex items-center gap-1.5 text-foreground font-medium">
            <IconWorkflow className="h-3.5 w-3.5 text-primary" />
            <span>{t('threeTierReady')}</span>
          </div>
        </div>
      </div>
    </div>
  );
});

TelemetryPostureCard.displayName = 'TelemetryPostureCard';
export default TelemetryPostureCard;
