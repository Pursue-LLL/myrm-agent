'use client';

/**
 * [INPUT]
 * @/services/memoryCommandCenter::MemoryCommandHealth (POS: Memory health DTO)
 *
 * [OUTPUT]
 * MemoryHealthDashboard: Memory health dashboard panel with score arc, dimension cards, suggestions and guardian status.
 *
 * [POS]
 * 记忆健康仪表板。展示总分弧形进度条、4 维度卡片（freshness/coverage/retention/coherence）、建议列表和 Guardian 运行状态。纯前端展示，后端零改动。
 */

import { memo, useMemo } from 'react';
import type { useTranslations } from 'next-intl';
import type { MemoryCommandHealth } from '@/services/memoryCommandCenter';
import { cn } from '@/lib/utils/classnameUtils';

type T = ReturnType<typeof useTranslations<'memory'>>;

const HEALTH_DIMENSIONS = ['freshness', 'coverage', 'retention', 'coherence'] as const;
type HealthDimension = (typeof HEALTH_DIMENSIONS)[number];

const STATUS_COLORS: Record<string, string> = {
  healthy: 'text-emerald-700 dark:text-emerald-300',
  degraded: 'text-amber-700 dark:text-amber-300',
  critical: 'text-destructive',
  unknown: 'text-muted-foreground',
};

const ARC_COLORS: Record<string, string> = {
  healthy: 'stroke-emerald-500',
  degraded: 'stroke-amber-500',
  critical: 'stroke-destructive',
  unknown: 'stroke-muted-foreground/40',
};

const DIMENSION_ICONS: Record<HealthDimension, string> = {
  freshness:
    'M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83',
  coverage: 'M4 6h16M4 10h16M4 14h10M4 18h6',
  retention: 'M12 22c5.52 0 10-4.48 10-10S17.52 2 12 2 2 6.48 2 12s4.48 10 10 10zM12 6v6l4 2',
  coherence: 'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.97-4.03 9-9 9s-9-4.03-9-9 4.03-9 9-9 9 4.03 9 9z',
};

function getScoreColor(score: number): string {
  if (score >= 80) return 'healthy';
  if (score >= 50) return 'degraded';
  if (score > 0) return 'critical';
  return 'unknown';
}

const ScoreArc = memo(({ score, status }: { score: number; status: string }) => {
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.max(0, Math.min(100, score));
  const dashOffset = circumference * (1 - pct / 100);
  const colorKey = score > 0 ? getScoreColor(score) : status;

  return (
    <div className="relative flex items-center justify-center">
      <svg viewBox="0 0 128 128" className="h-28 w-28 -rotate-90 sm:h-32 sm:w-32">
        <circle cx="64" cy="64" r={radius} fill="none" strokeWidth="8" className="stroke-border/30" />
        <circle
          cx="64"
          cy="64"
          r={radius}
          fill="none"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          className={cn(
            'transition-[stroke-dashoffset] duration-700 ease-out',
            ARC_COLORS[colorKey] ?? ARC_COLORS.unknown,
          )}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span
          className={cn(
            'text-2xl font-bold tabular-nums sm:text-3xl',
            STATUS_COLORS[colorKey] ?? STATUS_COLORS.unknown,
          )}
        >
          {score > 0 ? score : '—'}
        </span>
        <span className="text-[10px] text-muted-foreground">/100</span>
      </div>
    </div>
  );
});
ScoreArc.displayName = 'ScoreArc';

const DIMENSION_KEYS: Record<HealthDimension, string> = {
  freshness: 'freshness',
  coverage: 'coverage',
  retention: 'retention_health',
  coherence: 'coherence',
};

const DimensionCard = memo(({ dimension, value, t }: { dimension: HealthDimension; value: number; t: T }) => {
  const pct = Math.round(value * 100);
  const colorKey = getScoreColor(pct);

  return (
    <div className="rounded-lg border border-border/50 bg-accent/20 p-3">
      <div className="flex items-center gap-2">
        <svg
          viewBox="0 0 24 24"
          className="h-4 w-4 text-muted-foreground"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <path d={DIMENSION_ICONS[dimension]} strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="text-xs font-medium text-foreground">
          {t(`commandCenter.healthDashboard.dimensions.${DIMENSION_KEYS[dimension]}`)}
        </span>
      </div>
      <div className="mt-2 flex items-end justify-between gap-2">
        <span className={cn('text-lg font-bold tabular-nums', STATUS_COLORS[colorKey] ?? STATUS_COLORS.unknown)}>
          {pct}%
        </span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-border/30">
        <div
          className={cn(
            'h-full rounded-full transition-[width] duration-500',
            colorKey === 'healthy' && 'bg-emerald-500',
            colorKey === 'degraded' && 'bg-amber-500',
            colorKey === 'critical' && 'bg-destructive',
            colorKey === 'unknown' && 'bg-muted-foreground/40',
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
});
DimensionCard.displayName = 'DimensionCard';

const GuardianStatus = memo(({ health, t }: { health: MemoryCommandHealth; t: T }) => {
  const isRunning = health.guardian_running;
  const countdown = health.seconds_until_next;

  const countdownLabel = useMemo(() => {
    if (countdown == null || countdown <= 0) return null;
    if (countdown >= 3600) return `${Math.floor(countdown / 3600)}h ${Math.floor((countdown % 3600) / 60)}m`;
    if (countdown >= 60) return `${Math.floor(countdown / 60)}m ${countdown % 60}s`;
    return `${countdown}s`;
  }, [countdown]);

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <span
        className={cn(
          'h-2 w-2 rounded-full',
          isRunning ? 'bg-emerald-500 shadow-[0_0_6px_hsl(142,71%,45%/0.5)]' : 'bg-muted-foreground/40',
        )}
      />
      <span>
        {isRunning
          ? t('commandCenter.healthDashboard.guardianRunning')
          : t('commandCenter.healthDashboard.guardianStopped')}
      </span>
      {countdownLabel && (
        <span className="text-[10px] text-muted-foreground/70">
          {t('commandCenter.healthDashboard.guardianNextRun', { time: countdownLabel })}
        </span>
      )}
      {health.checked_at && (
        <span className="text-[10px] text-muted-foreground/60">
          {t('commandCenter.healthDashboard.checkedAt', {
            time: new Intl.DateTimeFormat(undefined, {
              hour: '2-digit',
              minute: '2-digit',
            }).format(new Date(health.checked_at)),
          })}
        </span>
      )}
      <span className="text-[10px] text-muted-foreground/60">
        {t(`commandCenter.healthDashboard.cacheStatus.${health.cache_status}`)}
      </span>
    </div>
  );
});
GuardianStatus.displayName = 'GuardianStatus';

interface MemoryHealthDashboardProps {
  health: MemoryCommandHealth;
  t: T;
}

const MemoryHealthDashboard = memo(({ health, t }: MemoryHealthDashboardProps) => {
  const score = health.total ?? 0;
  const hasDimensions = Object.keys(health.dimensions).length > 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-start">
        <ScoreArc score={score} status={health.status} />
        <div className="flex-1 space-y-2">
          <div className="text-sm font-semibold text-foreground">{t('commandCenter.healthDashboardTitle')}</div>
          <div className={cn('text-xs font-medium', STATUS_COLORS[health.status] ?? STATUS_COLORS.unknown)}>
            {t(`commandCenter.healthStatus.${health.status}`)}
          </div>
          <GuardianStatus health={health} t={t} />
          {health.sample_size > 0 && (
            <div className="text-[10px] text-muted-foreground/60">
              {t('commandCenter.healthDashboard.sampleSize', { count: health.sample_size })}
            </div>
          )}
        </div>
      </div>

      {hasDimensions && (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {HEALTH_DIMENSIONS.filter((dim) => {
            if (dim === 'coherence' && !health.has_graph) return false;
            return health.dimensions[DIMENSION_KEYS[dim]] != null;
          }).map((dim) => (
            <DimensionCard key={dim} dimension={dim} value={health.dimensions[DIMENSION_KEYS[dim]] ?? 0} t={t} />
          ))}
        </div>
      )}

      {health.suggestions.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-foreground">
            {t('commandCenter.healthDashboard.suggestionsTitle')}
          </div>
          <ul className="space-y-1.5">
            {health.suggestions.map((suggestion, i) => (
              <li
                key={i}
                className="flex items-start gap-2 rounded-lg border border-border/50 bg-accent/20 px-3 py-2 text-xs leading-5 text-muted-foreground"
              >
                <span className="mt-0.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-amber-500" />
                {suggestion}
              </li>
            ))}
          </ul>
        </div>
      )}

      {!hasDimensions && health.suggestions.length === 0 && (
        <div className="rounded-lg border border-dashed border-border/70 p-4 text-sm text-muted-foreground">
          {t('commandCenter.healthDashboard.unavailable')}
        </div>
      )}
    </div>
  );
});
MemoryHealthDashboard.displayName = 'MemoryHealthDashboard';

export default MemoryHealthDashboard;
