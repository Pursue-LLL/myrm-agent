'use client';

/**
 * [INPUT]
 * @/services/memory-health::getSharedContextMemoryHealth (POS: Frontend Shared Context health API client)
 *
 * [OUTPUT]
 * SharedContextMemoryHealthBanner: Shared Context memory dependency health banner.
 *
 * [POS]
 * Shared Context 记忆依赖健康提示组件。低成本展示配置状态，并支持用户手动执行实时 embedding 探测。
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { CheckCircle2, Loader2, RefreshCw, ShieldAlert, TriangleAlert } from 'lucide-react';

import { cn } from '@/lib/utils/classnameUtils';
import { getSharedContextMemoryHealth, type SharedContextMemoryHealthResponse } from '@/services/memory-health';

type HealthTone = 'ready' | 'warning' | 'error';

const toneClasses: Record<HealthTone, string> = {
  ready: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  warning: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  error: 'border-destructive/30 bg-destructive/10 text-destructive',
};

const iconClasses: Record<HealthTone, string> = {
  ready: 'text-emerald-600 dark:text-emerald-300',
  warning: 'text-amber-600 dark:text-amber-300',
  error: 'text-destructive',
};

const getTone = (health: SharedContextMemoryHealthResponse): HealthTone => {
  if (health.ready) return 'ready';
  if (health.status === 'not_configured') return 'warning';
  return 'error';
};

const HealthIcon = ({ tone }: { tone: HealthTone }) => {
  if (tone === 'ready') return <CheckCircle2 size={18} className={iconClasses.ready} />;
  if (tone === 'warning') return <TriangleAlert size={18} className={iconClasses.warning} />;
  return <ShieldAlert size={18} className={iconClasses.error} />;
};

export const SharedContextMemoryHealthBanner = memo(() => {
  const t = useTranslations('memory.sharedContexts.health');
  const tMemory = useTranslations('memory');
  const [health, setHealth] = useState<SharedContextMemoryHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [probing, setProbing] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  const loadHealth = useCallback(
    async (probe: boolean) => {
      if (probe) {
        setProbing(true);
      } else {
        setLoading(true);
      }
      setErrorMessage('');
      try {
        const nextHealth = await getSharedContextMemoryHealth(probe);
        setHealth(nextHealth);
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : tMemory('unknownError'));
      } finally {
        setLoading(false);
        setProbing(false);
      }
    },
    [tMemory],
  );

  useEffect(() => {
    void loadHealth(false);
  }, [loadHealth]);

  if (loading && health === null) {
    return (
      <div className="rounded-xl border border-border/60 bg-card/70 px-4 py-3 text-sm text-muted-foreground">
        <span className="inline-flex items-center gap-2">
          <Loader2 size={14} className="animate-spin" />
          {t('checking')}
        </span>
      </div>
    );
  }

  if (errorMessage && health === null) {
    return (
      <div className={cn('rounded-xl border px-4 py-3 text-sm', toneClasses.error)}>
        <div className="flex items-start gap-3">
          <ShieldAlert size={18} className={iconClasses.error} />
          <div>
            <p className="font-medium">{t('unavailable')}</p>
            <p className="mt-1 text-xs opacity-85">{errorMessage}</p>
          </div>
        </div>
      </div>
    );
  }

  if (health === null) return null;

  const tone = getTone(health);
  const reason = health.reason ? t(`reason.${health.reason}`) : t('reason.ready');

  return (
    <div className={cn('rounded-xl border px-4 py-3 text-sm', toneClasses[tone])}>
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex items-start gap-3">
          <HealthIcon tone={tone} />
          <div>
            <p className="font-medium">{t(`status.${health.status}`)}</p>
            <p className="mt-1 text-xs opacity-85">{reason}</p>
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] opacity-75">
              <span>{t('summary.model', { model: health.model })}</span>
              <span>{health.probed ? t('summary.liveProbe') : t('summary.configOnly')}</span>
              {typeof health.vector_dimension === 'number' && (
                <span>{t('summary.dimension', { dimension: health.vector_dimension })}</span>
              )}
            </div>
          </div>
        </div>
        <button
          onClick={() => void loadHealth(true)}
          disabled={probing}
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-current/20 px-3 py-2 text-xs font-medium transition hover:bg-background/50 disabled:opacity-50"
        >
          {probing ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
          {probing ? t('actions.checking') : t('actions.probe')}
        </button>
      </div>
    </div>
  );
});

SharedContextMemoryHealthBanner.displayName = 'SharedContextMemoryHealthBanner';
