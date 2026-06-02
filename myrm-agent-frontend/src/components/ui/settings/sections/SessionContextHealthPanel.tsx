'use client';

/**
 * [INPUT]
 * - services/contextHealth::ContextHealth (POS: Statistics context-health DTO layer. Defines compaction, pruning/archive restore, adaptive backoff, and prompt-cache health contracts for Session Analytics UI.)
 * - SessionContextHealthPanelRestore::PruningFooter (POS: Session analytics restore-guidance subview. Keeps range-specific restore UI outside the high-level context health panel layout.)
 *
 * [OUTPUT]
 * - SessionContextHealthPanel: renders session compaction, pruning/archive restore, and prompt-cache health signals.
 *
 * [POS]
 * Session Analytics context-health panel. Presents pruning ROI, adaptive pruning backoff, archive restore outcomes, and cache retention signals.
 */

import { memo, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { formatTokenCount } from './RoutingAnalyticsPanel';
import { PruningFooter } from './SessionContextHealthPanelRestore';
import type { ContextHealth, HealthStatus } from '@/services/contextHealth';

interface SessionContextHealthPanelProps {
  health: ContextHealth;
  sessionId: string;
}

const STATUS_STYLES: Record<
  HealthStatus,
  {
    badgeClass: string;
    dotClass: string;
  }
> = {
  inactive: {
    badgeClass: 'bg-muted text-muted-foreground',
    dotClass: 'bg-muted-foreground/50',
  },
  healthy: {
    badgeClass: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
    dotClass: 'bg-emerald-500',
  },
  warning: {
    badgeClass: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
    dotClass: 'bg-amber-500',
  },
  critical: {
    badgeClass: 'bg-rose-500/15 text-rose-600 dark:text-rose-400',
    dotClass: 'bg-rose-500',
  },
};
const RESTORE_COST_RATIO_WARNING = 0.5;
const RESTORE_ROI_RATIO_WARNING = 0.5;
const BACKOFF_REASON_LABEL_KEYS: Record<string, string> = {
  negative_net_savings: 'negativeNetSavings',
  high_refetch_ratio: 'highRefetchRatio',
  high_restore_cost_ratio: 'highRestoreCostRatio',
  low_restore_roi_ratio: 'lowRestoreRoiRatio',
};

const SessionContextHealthPanel = memo<SessionContextHealthPanelProps>(({ health, sessionId }) => {
  const t = useTranslations('settings.sessionAnalytics');
  const overallStyle = STATUS_STYLES[health.status];
  const pruningFooter = getPruningFooter(health, t);

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="space-y-1">
          <h3 className="text-sm font-semibold text-foreground">{t('contextHealth.title')}</h3>
          <p className="text-xs text-muted-foreground">{t('contextHealth.description')}</p>
        </div>
        <span
          className={cn(
            'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium',
            overallStyle.badgeClass,
          )}
        >
          <StatusDot status={health.status} />
          {t(`contextHealth.status.${health.status}`)}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <HealthCard
          title={t('contextHealth.compaction.title')}
          description={t('contextHealth.compaction.description')}
          status={health.compaction.status}
          rows={[
            [t('contextHealth.compaction.count'), health.compaction.count.toString()],
            [t('contextHealth.compaction.saved'), formatTokenCount(health.compaction.tokens_saved)],
            [t('contextHealth.compaction.netSaved'), formatTokenCount(health.compaction.net_tokens_saved)],
            [t('contextHealth.compaction.efficiency'), `${(health.compaction.efficiency * 100).toFixed(1)}%`],
            [
              t('contextHealth.compaction.refetch'),
              `${health.compaction.refetch_count} / ${(health.compaction.refetch_ratio * 100).toFixed(1)}%`,
            ],
            [t('contextHealth.compaction.dedup'), formatTokenCount(health.compaction.dedup_tokens_saved)],
            [t('contextHealth.compaction.integrity'), health.compaction.integrity_skipped.toString()],
            [t('contextHealth.compaction.persisted'), health.compaction.summary_persisted ? t('yes') : t('no')],
          ]}
          footer={
            health.compaction.last_compacted_at
              ? `${t('contextHealth.compaction.lastCompacted')}: ${new Date(health.compaction.last_compacted_at).toLocaleString()}`
              : null
          }
        />

        <HealthCard
          title={t('contextHealth.pruning.title')}
          description={t('contextHealth.pruning.description')}
          status={health.pruning.status}
          rows={[
            [t('contextHealth.pruning.signal'), getPruningSignalLabel(health, t)],
            [t('contextHealth.pruning.backoff'), getPruningBackoffLabel(health, t)],
            ...(health.pruning.backoff_applied
              ? ([[t('contextHealth.pruning.backoffReasons'), getPruningBackoffReasonLabel(health, t)]] satisfies [
                  string,
                  string,
                ][])
              : []),
            [t('contextHealth.pruning.archived'), health.pruning.archived.toString()],
            [t('contextHealth.pruning.archiveWritten'), health.pruning.archive_written_count.toString()],
            [t('contextHealth.pruning.archiveReused'), health.pruning.archive_reused_count.toString()],
            [t('contextHealth.pruning.softTrimmed'), health.pruning.soft_trimmed.toString()],
            [t('contextHealth.pruning.offloadFailed'), health.pruning.offload_failed.toString()],
            [t('contextHealth.pruning.deferred'), health.pruning.deferred_count.toString()],
            [t('contextHealth.pruning.archiveDeferred'), health.pruning.archive_deferred_count.toString()],
            [t('contextHealth.pruning.refetch'), health.pruning.archive_refetch_count.toString()],
            [t('contextHealth.pruning.restoreRequested'), health.pruning.archive_restore_requested_count.toString()],
            [t('contextHealth.pruning.restoreAllowed'), health.pruning.archive_restore_allowed_count.toString()],
            [t('contextHealth.pruning.restoreBlocked'), health.pruning.archive_restore_blocked_count.toString()],
            [t('contextHealth.pruning.restoreResults'), health.pruning.archive_restore_result_count.toString()],
            [
              t('contextHealth.pruning.restoreResultTokens'),
              formatTokenCount(health.pruning.archive_restore_result_tokens),
            ],
            [
              t('contextHealth.pruning.restoreBlockedRatio'),
              `${(health.pruning.archive_restore_blocked_ratio * 100).toFixed(1)}%`,
            ],
            [
              t('contextHealth.pruning.restoreCostRatio'),
              `${(health.pruning.pruning_restore_cost_ratio * 100).toFixed(1)}%`,
            ],
            [
              t('contextHealth.pruning.restoreRoiRatio'),
              `${(health.pruning.pruning_restore_roi_ratio * 100).toFixed(1)}%`,
            ],
            [t('contextHealth.pruning.refetchTokens'), formatTokenCount(health.pruning.archive_refetch_tokens)],
            [t('contextHealth.pruning.saved'), formatTokenCount(health.pruning.tokens_saved)],
            [t('contextHealth.pruning.netSaved'), formatTokenCount(health.pruning.net_tokens_saved)],
            [t('contextHealth.pruning.refetchRatio'), `${(health.pruning.refetch_ratio * 100).toFixed(1)}%`],
            [t('contextHealth.pruning.writtenBytes'), formatByteCount(health.pruning.archive_bytes_written)],
            [t('contextHealth.pruning.reusedBytes'), formatByteCount(health.pruning.archive_bytes_reused)],
            [t('contextHealth.pruning.originalTokens'), formatTokenCount(health.pruning.original_tokens)],
            [t('contextHealth.pruning.archiveSummaryQueued'), health.pruning.archive_summary_queued_count.toString()],
            [
              t('contextHealth.pruning.archiveSummarySucceeded'),
              health.pruning.archive_summary_succeeded_count.toString(),
            ],
            [t('contextHealth.pruning.archiveSummaryFailed'), health.pruning.archive_summary_failed_count.toString()],
            [t('contextHealth.pruning.archiveSummarySkipped'), health.pruning.archive_summary_skipped_count.toString()],
          ]}
          footer={<PruningFooter health={health} message={pruningFooter} sessionId={sessionId} />}
        />

        <HealthCard
          title={t('contextHealth.cache.title')}
          description={t('contextHealth.cache.description')}
          status={health.cache.status}
          rows={[
            [t('contextHealth.cache.strategy'), getCacheStrategyLabel(health, t)],
            [t('contextHealth.cache.calls'), health.cache.calls.toString()],
            [t('contextHealth.cache.inputTokens'), formatTokenCount(health.cache.input_tokens)],
            [t('contextHealth.cache.cachedTokens'), formatTokenCount(health.cache.cached_tokens)],
            [t('contextHealth.cache.hitRate'), `${(health.cache.cache_hit_rate * 100).toFixed(1)}%`],
            [t('contextHealth.cache.provider'), health.cache.model_family],
            [t('contextHealth.cache.ttl'), formatSeconds(health.cache.ttl_seconds)],
            [t('contextHealth.cache.policy'), health.cache.policy_reason],
            [t('contextHealth.cache.observation'), getRetentionObservationLabel(health, t)],
            [t('contextHealth.cache.sample'), getRetentionSampleLabel(health, t)],
          ]}
          footer={
            <div className="space-y-2">
              <div className="h-2 rounded-full bg-muted overflow-hidden">
                <div
                  className={cn(
                    'h-full rounded-full transition-all',
                    health.cache.status === 'critical'
                      ? 'bg-rose-500'
                      : health.cache.status === 'warning'
                        ? 'bg-amber-500'
                        : 'bg-emerald-500',
                  )}
                  style={{ width: `${Math.min(health.cache.cache_hit_rate * 100, 100)}%` }}
                />
              </div>
              <p className="text-xs text-muted-foreground">{t('contextHealth.cache.caption')}</p>
            </div>
          }
        />
      </div>
    </section>
  );
});
SessionContextHealthPanel.displayName = 'SessionContextHealthPanel';

function getPruningFooter(health: ContextHealth, t: ReturnType<typeof useTranslations>): string | null {
  if (!health.pruning.active) {
    return null;
  }
  if (health.pruning.offload_failed > 0) {
    return t('contextHealth.pruning.offloadWarning');
  }
  if (health.pruning.deferred_count > 0) {
    return t('contextHealth.pruning.deferredWarning');
  }
  if (health.pruning.archive_deferred_count > health.pruning.archive_deferred_soft_trimmed_count) {
    return t('contextHealth.pruning.archiveDeferredWarning');
  }
  if (health.pruning.archive_restore_blocked_count > 0) {
    return t('contextHealth.pruning.restoreBlockedWarning');
  }
  if (health.pruning.backoff_applied) {
    return t('contextHealth.pruning.adaptiveBackoffWarning', {
      reasons: getPruningBackoffReasonLabel(health, t),
    });
  }
  if (health.pruning.net_tokens_saved < 0) {
    return t('contextHealth.pruning.negativeSavingsWarning');
  }
  if (hasRestoreCostWarning(health)) {
    return t('contextHealth.pruning.restoreCostWarning');
  }
  if (health.pruning.refetch_ratio >= 0.5) {
    return t('contextHealth.pruning.refetchWarning');
  }
  return t('contextHealth.pruning.caption');
}

function getPruningSignalLabel(health: ContextHealth, t: ReturnType<typeof useTranslations>): string {
  if (!health.pruning.active) {
    return t('contextHealth.pruning.signals.inactive');
  }
  if (health.pruning.archive_restore_blocked_count > 0) {
    return t('contextHealth.pruning.signals.restoreBlocked');
  }
  if (health.pruning.backoff_applied) {
    return t('contextHealth.pruning.signals.adaptiveBackoff');
  }
  if (hasRestoreCostWarning(health)) {
    return t('contextHealth.pruning.signals.restoreCostHigh');
  }
  const archiveAvailable =
    health.pruning.archived + health.pruning.archive_written_count + health.pruning.archive_reused_count > 0;
  if (archiveAvailable && health.cache.active && health.cache.status !== 'healthy') {
    return t('contextHealth.pruning.signals.cacheColdArchived');
  }
  if (archiveAvailable) {
    return t('contextHealth.pruning.signals.archiveAvailable');
  }
  if (health.cache.active && health.cache.status === 'healthy' && health.cache.cached_tokens > 0) {
    return t('contextHealth.pruning.signals.cacheHotSkip');
  }
  if (health.pruning.archive_deferred_count > health.pruning.archive_deferred_soft_trimmed_count) {
    return t('contextHealth.pruning.signals.archiveDeferred');
  }
  if (health.pruning.soft_trimmed > 0) {
    return t('contextHealth.pruning.signals.softTrimmed');
  }
  return t('contextHealth.pruning.signals.monitoring');
}

function getPruningBackoffLabel(health: ContextHealth, t: ReturnType<typeof useTranslations>): string {
  return health.pruning.backoff_applied
    ? t('contextHealth.pruning.backoffActive')
    : t('contextHealth.pruning.backoffInactive');
}

function getPruningBackoffReasonLabel(health: ContextHealth, t: ReturnType<typeof useTranslations>): string {
  const reasons = Object.entries(health.pruning.backoff_reasons)
    .filter(([, count]) => count > 0)
    .map(([reason]) => {
      const key = BACKOFF_REASON_LABEL_KEYS[reason] ?? 'unknown';
      return t(`contextHealth.pruning.backoffReasonLabels.${key}`);
    });
  return reasons.length > 0 ? reasons.join(', ') : t('contextHealth.pruning.backoffReasonLabels.unknown');
}

function hasRestoreCostWarning(health: ContextHealth): boolean {
  return (
    health.pruning.archive_restore_result_count > 0 &&
    (health.pruning.tokens_saved <= 0 ||
      health.pruning.pruning_restore_cost_ratio >= RESTORE_COST_RATIO_WARNING ||
      health.pruning.pruning_restore_roi_ratio < RESTORE_ROI_RATIO_WARNING)
  );
}

function getCacheStrategyLabel(health: ContextHealth, t: ReturnType<typeof useTranslations>): string {
  if (!health.cache.active) {
    return t('contextHealth.cache.strategies.inactive');
  }
  if (health.cache.status === 'healthy' && health.cache.cached_tokens > 0) {
    return t('contextHealth.cache.strategies.hotProtected');
  }
  if (health.cache.retention_observation_state === 'insufficient_data') {
    return t('contextHealth.cache.strategies.insufficientData');
  }
  if (health.cache.cached_tokens === 0 && health.cache.input_tokens > 0) {
    return t('contextHealth.cache.strategies.coldEligible');
  }
  if (health.cache.status === 'warning' || health.cache.status === 'critical') {
    return t('contextHealth.cache.strategies.coldWatch');
  }
  return t('contextHealth.cache.strategies.stable');
}

function getRetentionObservationLabel(health: ContextHealth, t: ReturnType<typeof useTranslations>): string {
  const state = health.cache.retention_observation_state;
  const labelKey = state === 'observed' ? 'observed' : state === 'estimated' ? 'estimated' : 'insufficientData';
  return t(`contextHealth.cache.observationStates.${labelKey}`);
}

function getRetentionSampleLabel(health: ContextHealth, t: ReturnType<typeof useTranslations>): string {
  const sourceKey = health.cache.observation_sample_source === 'dominant_model' ? 'dominantModel' : 'sessionAggregate';
  const modelName = health.cache.observation_model_name ? ` · ${health.cache.observation_model_name}` : '';
  return `${t(`contextHealth.cache.sampleSources.${sourceKey}`)}${modelName}: ${health.cache.observed_calls} / ${formatTokenCount(
    health.cache.observed_input_tokens,
  )} / ${formatTokenCount(health.cache.observed_cached_tokens)} / ${(
    health.cache.observed_cache_hit_rate * 100
  ).toFixed(1)}%`;
}

function formatByteCount(bytes: number): string {
  if (bytes < 1024) {
    return `${Math.max(bytes, 0)} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatSeconds(value: number): string {
  if (!Number.isFinite(value) || value <= 0) {
    return '-';
  }
  if (value < 60) {
    return `${value.toFixed(0)}s`;
  }
  const minutes = value / 60;
  if (minutes < 60) {
    return `${minutes.toFixed(minutes < 10 ? 1 : 0)}m`;
  }
  const hours = minutes / 60;
  return `${hours.toFixed(hours < 10 ? 1 : 0)}h`;
}

interface HealthCardProps {
  title: string;
  description: string;
  status: HealthStatus;
  rows: [string, string][];
  footer: ReactNode;
}

const HealthCard = memo<HealthCardProps>(({ title, description, status, rows, footer }) => {
  const t = useTranslations('settings.sessionAnalytics');
  const style = STATUS_STYLES[status];

  return (
    <div className="rounded-lg border border-border/40 bg-background/60 p-4 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <div className={cn('rounded-lg p-2', style.badgeClass)}>
              <StatusDot status={status} />
            </div>
            <h4 className="text-sm font-semibold text-foreground">{title}</h4>
          </div>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
        <span
          className={cn('inline-flex items-center rounded-full px-2 py-1 text-[11px] font-medium', style.badgeClass)}
        >
          {t(`contextHealth.status.${status}`)}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-3">
        {rows.map(([label, value]) => (
          <div key={label} className="space-y-1">
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
            <p className="break-words text-sm font-medium text-foreground tabular-nums">{value}</p>
          </div>
        ))}
      </div>

      {footer ? <div>{footer}</div> : null}
    </div>
  );
});
HealthCard.displayName = 'HealthCard';

interface StatusDotProps {
  status: HealthStatus;
}

const StatusDot = memo<StatusDotProps>(({ status }) => (
  <span className={cn('h-2.5 w-2.5 shrink-0 rounded-full', STATUS_STYLES[status].dotClass)} aria-hidden />
));
StatusDot.displayName = 'StatusDot';

export default SessionContextHealthPanel;
