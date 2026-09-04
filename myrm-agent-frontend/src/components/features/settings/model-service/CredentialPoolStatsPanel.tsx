import React, { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Activity, AlertTriangle, CheckCircle2, Clock, RefreshCw } from 'lucide-react';

import {
  CredentialPoolKeyStat,
  CredentialPoolStatItem,
  fetchCredentialPoolStats,
  resetCredentialPoolCooldowns,
} from '@/services/llm-config';
import { useToast } from '@/hooks/shared/useToast';
import { cn } from '@/lib/utils';

interface CredentialPoolStatsPanelProps {
  providerId?: string;
  hasMultipleKeys: boolean;
}

export const CredentialPoolStatsPanel = memo<CredentialPoolStatsPanelProps>(({ providerId, hasMultipleKeys }) => {
  const t = useTranslations('settings.modelService');
  const { toast } = useToast();
  const [pools, setPools] = useState<CredentialPoolStatItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [isOpen, setIsOpen] = useState(false);

  const loadStats = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchCredentialPoolStats();
      setPools(data);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      loadStats();
    }
  }, [isOpen, loadStats]);

  const handleResetCooldowns = async (suffix?: string) => {
    setResetting(true);
    try {
      const res = await resetCredentialPoolCooldowns(suffix);
      toast({
        title: t('resetCooldownsSuccess', { count: res.reset_count }),
        duration: 3000,
      });
      await loadStats();
    } finally {
      setResetting(false);
    }
  };

  if (!hasMultipleKeys) {
    return null;
  }

  // Aggregate key stats across all pools matching providerId or overall
  const matchingPools = providerId
    ? pools.filter((p) => p.cache_key.toLowerCase().includes(providerId.toLowerCase()))
    : pools;
  const activePools = matchingPools.length > 0 ? matchingPools : pools;

  return (
    <div className="rounded-lg border border-border/40 bg-muted/20 p-3 space-y-2 text-xs">
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center gap-1.5 font-medium text-foreground hover:text-primary transition-colors"
          data-testid="toggle-pool-stats"
        >
          <Activity className="w-3.5 h-3.5 text-primary" />
          <span>{t('poolStatsTitle')}</span>
          <span className="text-[10px] text-muted-foreground px-1.5 py-0.5 rounded-full bg-muted border border-border/40">
            {isOpen ? '收起' : '展开'}
          </span>
        </button>

        {isOpen && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => handleResetCooldowns()}
              disabled={resetting}
              className="flex items-center gap-1 px-2 py-1 rounded bg-primary/10 text-primary hover:bg-primary/20 transition-colors disabled:opacity-50 text-[11px]"
              data-testid="reset-cooldowns-btn"
            >
              <RefreshCw className={cn('w-3 h-3', resetting && 'animate-spin')} />
              <span>{t('resetCooldowns')}</span>
            </button>
          </div>
        )}
      </div>

      {isOpen && (
        <div className="pt-2 space-y-2 border-t border-border/30">
          {loading ? (
            <div className="py-2 text-center text-muted-foreground">{t('checking')}</div>
          ) : activePools.length === 0 ? (
            <div className="py-2 text-center text-muted-foreground">{t('noActivePools')}</div>
          ) : (
            activePools.map((pool, idx) => (
              <div key={pool.cache_key || idx} className="space-y-1.5 bg-background/60 p-2.5 rounded-md border border-border/30">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="font-mono font-medium text-foreground">{pool.model || pool.cache_key}</span>
                  <span className="text-muted-foreground uppercase">{pool.stats.strategy}</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                  {pool.stats.keys.map((k: CredentialPoolKeyStat) => (
                    <div
                      key={k.suffix}
                      className={cn(
                        'flex items-center justify-between p-1.5 rounded border text-[11px]',
                        k.in_cooldown
                          ? 'border-amber-500/40 bg-amber-500/5 text-amber-700 dark:text-amber-300'
                          : 'border-border/40 bg-muted/30 text-muted-foreground',
                      )}
                    >
                      <div className="flex items-center gap-1.5">
                        {k.in_cooldown ? (
                          <AlertTriangle className="w-3 h-3 text-amber-500" />
                        ) : (
                          <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                        )}
                        <span className="font-mono font-medium text-foreground">...{k.suffix}</span>
                      </div>

                      <div className="flex items-center gap-2">
                        <span>{t('poolCalls', { count: k.calls })}</span>
                        {k.rate_limits > 0 && (
                          <span className="text-amber-600 dark:text-amber-400">
                            {t('poolRateLimits', { count: k.rate_limits })}
                          </span>
                        )}
                        {k.in_cooldown && (
                          <button
                            type="button"
                            onClick={() => handleResetCooldowns(k.suffix)}
                            className="flex items-center gap-0.5 text-[10px] text-primary hover:underline"
                            title={t('resetCooldowns')}
                          >
                            <Clock className="w-2.5 h-2.5" />
                            <span>{Math.ceil(k.cooldown_remaining_s)}s</span>
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
});

CredentialPoolStatsPanel.displayName = 'CredentialPoolStatsPanel';
