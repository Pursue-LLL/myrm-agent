import React, { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Activity, AlertTriangle, CheckCircle2, Clock, RefreshCw, ShieldAlert, ShieldCheck } from 'lucide-react';

import {
  CircuitBreakerStat,
  fetchCircuitBreakersStatus,
  resetCircuitBreaker,
} from '@/services/llm-config';
import { useToast } from '@/hooks/shared/useToast';
import { cn } from '@/lib/utils';

interface CircuitBreakerDashboardProps {
  providerId?: string;
  className?: string;
}

export const CircuitBreakerDashboard = memo<CircuitBreakerDashboardProps>(({ providerId, className }) => {
  const t = useTranslations('settings.modelService');
  const { toast } = useToast();
  const [breakers, setBreakers] = useState<Record<string, CircuitBreakerStat>>({});
  const [loading, setLoading] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [isOpen, setIsOpen] = useState(false);

  const loadStats = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchCircuitBreakersStatus();
      setBreakers(data);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      loadStats();
    }
  }, [isOpen, loadStats]);

  const handleReset = async (key?: string) => {
    setResetting(true);
    try {
      const res = await resetCircuitBreaker(key);
      toast({
        title: t('resetCircuitBreakerSuccess', { count: res.reset_count }),
        duration: 3000,
      });
      await loadStats();
    } finally {
      setResetting(false);
    }
  };

  const breakerEntries = Object.entries(breakers);
  const filteredEntries = providerId
    ? breakerEntries.filter(([k]) => k.toLowerCase().includes(providerId.toLowerCase()))
    : breakerEntries;

  const displayEntries = filteredEntries.length > 0 ? filteredEntries : breakerEntries;
  const hasOpenBreakers = displayEntries.some(([, b]) => b.state === 'open');

  return (
    <div className={cn('rounded-lg border border-border/40 bg-muted/20 p-3 space-y-2 text-xs', className)}>
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center gap-1.5 font-medium text-foreground hover:text-primary transition-colors"
          data-testid="toggle-circuit-breaker-dashboard"
        >
          {hasOpenBreakers ? (
            <ShieldAlert className="w-3.5 h-3.5 text-amber-500" />
          ) : (
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
          )}
          <span>{t('circuitBreakerTitle')}</span>
          <span
            className={cn(
              'text-[10px] px-1.5 py-0.5 rounded-full border',
              hasOpenBreakers
                ? 'bg-amber-500/10 text-amber-500 border-amber-500/30'
                : 'bg-emerald-500/10 text-emerald-500 border-emerald-500/30',
            )}
          >
            {hasOpenBreakers ? t('circuitBreakerWarning') : t('circuitBreakerHealthy')}
          </span>
          <span className="text-[10px] text-muted-foreground px-1.5 py-0.5 rounded-full bg-muted border border-border/40">
            {isOpen ? '收起' : '展开'}
          </span>
        </button>

        {isOpen && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => handleReset()}
              disabled={resetting}
              className="flex items-center gap-1 px-2 py-1 rounded bg-primary/10 text-primary hover:bg-primary/20 transition-colors disabled:opacity-50 text-[11px]"
              data-testid="reset-circuit-breakers-btn"
            >
              <RefreshCw className={cn('w-3 h-3', resetting && 'animate-spin')} />
              <span>{t('resetAllCircuitBreakers')}</span>
            </button>
          </div>
        )}
      </div>

      {isOpen && (
        <div className="pt-2 space-y-2 border-t border-border/30">
          {loading ? (
            <div className="py-2 text-center text-muted-foreground">{t('checking')}</div>
          ) : displayEntries.length === 0 ? (
            <div className="py-2 text-center text-muted-foreground flex items-center justify-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
              <span>{t('noActiveCircuitBreakers')}</span>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
              {displayEntries.map(([key, stat]) => {
                const isOpenState = stat.state === 'open';
                const isHalfOpen = stat.state === 'half_open';
                return (
                  <div
                    key={key}
                    className={cn(
                      'p-2 rounded-md border text-[11px] space-y-1 bg-background/80',
                      isOpenState
                        ? 'border-red-500/30 bg-red-500/5'
                        : isHalfOpen
                          ? 'border-amber-500/30 bg-amber-500/5'
                          : 'border-emerald-500/20 bg-emerald-500/5',
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-medium text-foreground truncate max-w-[140px]" title={key}>
                        {key}
                      </span>
                      <span
                        className={cn(
                          'px-1.5 py-0.5 rounded text-[10px] font-medium uppercase',
                          isOpenState
                            ? 'bg-red-500/20 text-red-500'
                            : isHalfOpen
                              ? 'bg-amber-500/20 text-amber-500'
                              : 'bg-emerald-500/20 text-emerald-500',
                        )}
                      >
                        {stat.state}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-muted-foreground text-[10px]">
                      <span>{t('failureCount', { count: stat.failure_count })}</span>
                      {isOpenState && stat.retry_after_ms > 0 && (
                        <span className="text-amber-500 flex items-center gap-0.5 font-mono">
                          <Clock className="w-2.5 h-2.5" />
                          {Math.ceil(stat.retry_after_ms / 1000)}s
                        </span>
                      )}
                    </div>

                    {isOpenState && (
                      <div className="pt-1 flex justify-end">
                        <button
                          type="button"
                          onClick={() => handleReset(key)}
                          disabled={resetting}
                          className="text-[10px] text-primary hover:underline"
                        >
                          {t('resetThisBreaker')}
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
});

CircuitBreakerDashboard.displayName = 'CircuitBreakerDashboard';
