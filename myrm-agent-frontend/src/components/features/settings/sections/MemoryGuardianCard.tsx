'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { motion } from 'framer-motion';
import {
  IconAlertTriangle,
  IconBrain,
  IconCheckCircle,
  IconRefresh,
  IconShield,
  IconGlow,
} from '@/components/features/icons/PremiumIcons';
import { toast } from 'sonner';
import SettingsSection from './SettingsSection';
import { cn } from '@/lib/utils/classnameUtils';
import { getMemoryHealth, triggerMemoryMaintenance, type MemoryHealthResponse } from '@/services/memory';

const DIMENSION_LABELS: Record<string, { en: string; zh: string; icon: typeof IconBrain }> = {
  freshness: { en: 'Freshness', zh: '新鲜度', icon: IconGlow },
  coverage: { en: 'Coverage', zh: '覆盖率', icon: IconShield },
  retention_health: { en: 'Retention', zh: '保留健康', icon: IconBrain },
  coherence: { en: 'Coherence', zh: '一致性', icon: IconCheckCircle },
};

function getHealthColor(score: number): string {
  if (score >= 80) return 'text-emerald-600 dark:text-emerald-400';
  if (score >= 60) return 'text-amber-600 dark:text-amber-400';
  return 'text-red-600 dark:text-red-400';
}

function getHealthBg(score: number): string {
  if (score >= 80) return 'bg-emerald-500';
  if (score >= 60) return 'bg-amber-500';
  return 'bg-red-500';
}

function getHealthLabel(score: number, t: ReturnType<typeof useTranslations>): string {
  if (score >= 80) return t('healthGood');
  if (score >= 60) return t('healthFair');
  return t('healthPoor');
}

function formatTimeAgo(timestamp: number | null, t: ReturnType<typeof useTranslations>): string {
  if (!timestamp) return t('never');
  const seconds = Math.floor(Date.now() / 1000 - timestamp);
  if (seconds < 60) return t('justNow');
  if (seconds < 3600) return t('minutesAgo', { count: Math.floor(seconds / 60) });
  if (seconds < 86400) return t('hoursAgo', { count: Math.floor(seconds / 3600) });
  return t('daysAgo', { count: Math.floor(seconds / 86400) });
}

function formatCountdown(seconds: number | null, t: ReturnType<typeof useTranslations>): string {
  if (!seconds || seconds <= 0) return t('soon');
  if (seconds < 3600) return t('inMinutes', { count: Math.ceil(seconds / 60) });
  return t('inHours', { count: Math.round(seconds / 3600) });
}

const MemoryGuardianCard = memo(() => {
  const t = useTranslations('settings.memoryGuardian');
  const [data, setData] = useState<MemoryHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);

  const fetchHealth = useCallback(async () => {
    try {
      setError(null);
      const res = await getMemoryHealth();
      setData(res);
    } catch {
      setError(t('loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchHealth();
    let timeoutId: NodeJS.Timeout;
    const handleSseEvent = () => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => fetchHealth(), 1000);
    };
    window.addEventListener('health_status_updated', handleSseEvent);
    window.addEventListener('app_resync_required', handleSseEvent);
    return () => {
      window.removeEventListener('health_status_updated', handleSseEvent);
      window.removeEventListener('app_resync_required', handleSseEvent);
      clearTimeout(timeoutId);
    };
  }, [fetchHealth]);

  const handleTrigger = useCallback(async () => {
    setTriggering(true);
    try {
      const res = await triggerMemoryMaintenance();
      if (res.error) {
        toast.error(res.error);
      } else {
        toast.success(t('triggerSuccess'));
        await fetchHealth();
      }
    } catch {
      toast.error(t('triggerFailed'));
    } finally {
      setTriggering(false);
    }
  }, [t, fetchHealth]);

  if (loading) {
    return (
      <SettingsSection title={t('title')} description={t('description')}>
        <div className="h-32 rounded-xl bg-background/60 animate-pulse" />
      </SettingsSection>
    );
  }

  if (!data) {
    return (
      <SettingsSection
        title={t('title')}
        description={t('description')}
        action={
          <button
            onClick={fetchHealth}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors',
              'bg-primary/10 text-primary hover:bg-primary/20',
            )}
          >
            <IconRefresh className="w-3 h-3" />
            {t('retry')}
          </button>
        }
      >
        <div className="flex items-center gap-2 rounded-xl border border-dashed border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm text-amber-700 dark:text-amber-400">
          <IconAlertTriangle className="w-4 h-4" />
          <span>{error ?? t('loadFailed')}</span>
        </div>
      </SettingsSection>
    );
  }

  const { health, guardian } = data;
  const totalScore = Math.round(health.total);

  return (
    <SettingsSection
      title={t('title')}
      description={t('description')}
      action={
        <button
          onClick={handleTrigger}
          disabled={triggering}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors',
            'bg-primary/10 text-primary hover:bg-primary/20 disabled:opacity-50 disabled:cursor-not-allowed',
          )}
        >
          <IconRefresh className={`w-3 h-3 ${triggering ? 'animate-spin' : ''}`} />
          {triggering ? t('running') : t('triggerBtn')}
        </button>
      }
    >
      {/* Total Score Ring */}
      <div className="flex items-center gap-6">
        <div className="relative w-20 h-20 shrink-0">
          <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
            <circle
              cx="18"
              cy="18"
              r="15.5"
              fill="none"
              stroke="currentColor"
              className="text-border/40"
              strokeWidth="2.5"
            />
            <motion.circle
              cx="18"
              cy="18"
              r="15.5"
              fill="none"
              strokeWidth="2.5"
              strokeLinecap="round"
              className={getHealthBg(totalScore)}
              stroke="currentColor"
              strokeDasharray={`${totalScore * 0.974} 100`}
              initial={{ strokeDasharray: '0 100' }}
              animate={{ strokeDasharray: `${totalScore * 0.974} 100` }}
              transition={{ duration: 1, ease: 'easeOut' }}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={cn('text-lg font-bold tabular-nums', getHealthColor(totalScore))}>{totalScore}</span>
          </div>
        </div>

        <div className="flex-1 min-w-0 space-y-1.5">
          <div className="flex items-center gap-2">
            <span className={cn('text-sm font-semibold', getHealthColor(totalScore))}>
              {getHealthLabel(totalScore, t)}
            </span>
          </div>

          {/* Dimension bars */}
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
            {Object.entries(health.dimensions).map(([key, val]) => {
              const label = DIMENSION_LABELS[key];
              const score = Math.round(val);
              return (
                <div key={key} className="flex items-center gap-2">
                  <span className="text-[10px] text-muted-foreground w-14 truncate">{label?.en ?? key}</span>
                  <div className="flex-1 h-1.5 rounded-full bg-border/40 overflow-hidden">
                    <motion.div
                      className={cn('h-full rounded-full', getHealthBg(score))}
                      initial={{ width: 0 }}
                      animate={{ width: `${score}%` }}
                      transition={{ duration: 0.8, ease: 'easeOut' }}
                    />
                  </div>
                  <span className="text-[10px] tabular-nums text-muted-foreground w-6 text-right">{score}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Suggestions */}
      {health.suggestions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {health.suggestions.map((s, i) => (
            <div
              key={i}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-500/10 text-amber-700 dark:text-amber-400 text-[11px]"
            >
              <IconAlertTriangle className="w-2.5 h-2.5" />
              <span>{s}</span>
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-2 text-[11px] text-amber-700 dark:text-amber-400">
          <div className="flex items-center gap-2 min-w-0">
            <IconAlertTriangle className="w-3 h-3 shrink-0" />
            <span className="truncate">{error}</span>
          </div>
          <button onClick={fetchHealth} className="font-medium hover:underline shrink-0">
            {t('retry')}
          </button>
        </div>
      )}

      {/* Guardian Status */}
      <div className="flex items-center gap-4 text-[11px] text-muted-foreground border-t border-border/30 pt-3">
        <div className="flex items-center gap-1">
          <div className={cn('w-1.5 h-1.5 rounded-full', guardian.running ? 'bg-emerald-500' : 'bg-red-500')} />
          <span>{guardian.running ? t('guardianActive') : t('guardianInactive')}</span>
        </div>
        <span>
          {t('lastRun')}: {formatTimeAgo(guardian.last_run, t)}
        </span>
        {guardian.seconds_until_next !== null && (
          <span>
            {t('nextRun')}: {formatCountdown(guardian.seconds_until_next, t)}
          </span>
        )}
      </div>
    </SettingsSection>
  );
});

MemoryGuardianCard.displayName = 'MemoryGuardianCard';

export default MemoryGuardianCard;
