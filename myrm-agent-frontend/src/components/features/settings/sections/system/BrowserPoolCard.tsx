'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { IconGlobe, IconMonitor, IconWifi, IconWifiOff, IconRefresh } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';

interface BrowserPoolStats {
  total_browsers: number;
  external_browsers: number;
  current_pages_in_use: number;
  launch_mode: string;
  max_concurrent_pages: number;
}

interface BrowserHealthData {
  status: 'healthy' | 'degraded' | 'unhealthy';
  pool?: BrowserPoolStats;
  browsers_alive?: number;
  browsers_total?: number;
}

const LAUNCH_MODE_ICONS: Record<string, typeof IconGlobe> = {
  auto: IconWifi,
  launch: IconMonitor,
  connect: IconGlobe,
};

const BrowserPoolCard = memo(() => {
  const t = useTranslations('settings.browserPool');
  const [health, setHealth] = useState<BrowserHealthData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchHealth = useCallback(async () => {
    try {
      const resp = await fetch('/api/v1/health/browser');
      if (resp.ok) {
        setHealth(await resp.json());
      }
    } catch {
      setHealth(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    let timeoutId: NodeJS.Timeout;
    const handleResync = () => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => fetchHealth(), 1000);
    };
    window.addEventListener('app_resync_required', handleResync);
    return () => {
      window.removeEventListener('app_resync_required', handleResync);
      clearTimeout(timeoutId);
    };
  }, [fetchHealth]);

  const launchMode = health?.pool?.launch_mode ?? 'launch';
  const ModeIcon = LAUNCH_MODE_ICONS[launchMode] ?? IconMonitor;
  const externalCount = health?.pool?.external_browsers ?? 0;
  const hasExternal = externalCount > 0;

  const statusColor =
    health?.status === 'healthy'
      ? 'text-emerald-500'
      : health?.status === 'degraded'
        ? 'text-amber-500'
        : 'text-red-500';

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between px-2">
        <div className="flex items-center gap-3">
          <IconGlobe className="w-5 h-5 text-muted-foreground" />
          <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">{t('title')}</h2>
        </div>
        <button
          onClick={() => {
            setLoading(true);
            fetchHealth();
          }}
          disabled={loading}
          className="p-1.5 rounded-lg hover:bg-white/5 transition-colors"
        >
          <IconRefresh className={cn('w-3.5 h-3.5 text-muted-foreground', loading && 'animate-spin')} />
        </button>
      </div>

      <div className="rounded-2xl border border-white/5 bg-card/50 p-5 space-y-4">
        {/* Connection Mode */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className={cn(
                'w-9 h-9 rounded-xl flex items-center justify-center',
                hasExternal ? 'bg-indigo-500/10' : 'bg-white/5',
              )}
            >
              <ModeIcon
                className={cn('w-[18px] h-[18px]', hasExternal ? 'text-indigo-400' : 'text-muted-foreground')}
              />
            </div>
            <div>
              <p className="text-sm font-bold">{t(`modes.${launchMode}`)}</p>
              <p className="text-xs text-muted-foreground">{t(`modes.${launchMode}Desc`)}</p>
            </div>
          </div>
          <div className={cn('flex items-center gap-1.5 text-xs font-bold', statusColor)}>
            {hasExternal ? <IconWifi className="w-3.5 h-3.5" /> : <IconWifiOff className="w-3.5 h-3.5" />}
            {hasExternal ? t('status.connected') : t('status.managed')}
          </div>
        </div>

        {/* Stats */}
        {health?.pool && (
          <>
            <div className="h-px bg-white/5" />
            <div className="grid grid-cols-3 gap-4">
              <StatItem label={t('stats.browsers')} value={health.pool.total_browsers} />
              <StatItem
                label={t('stats.externalBrowsers')}
                value={health.pool.external_browsers}
                highlight={hasExternal}
              />
              <StatItem label={t('stats.pagesInUse')} value={health.pool.current_pages_in_use} />
            </div>
          </>
        )}
      </div>
    </section>
  );
});

BrowserPoolCard.displayName = 'BrowserPoolCard';

const StatItem = memo<{ label: string; value: number; highlight?: boolean }>(({ label, value, highlight }) => (
  <div className="text-center">
    <p className={cn('text-lg font-black tabular-nums', highlight ? 'text-indigo-400' : 'text-foreground')}>{value}</p>
    <p className="text-[10px] text-muted-foreground uppercase tracking-wider mt-0.5">{label}</p>
  </div>
));

StatItem.displayName = 'StatItem';

export default BrowserPoolCard;
