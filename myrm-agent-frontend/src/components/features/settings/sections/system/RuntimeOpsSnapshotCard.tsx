'use client';

/**
 * [INPUT]
 * - @/services/opsSnapshot::getOpsSnapshot (POS: ops aggregated snapshot API client)
 *
 * [OUTPUT]
 * - RuntimeOpsSnapshotCard: read-only runtime snapshot for local/desktop/cloud WebUI settings
 *
 * [POS]
 * Surfaces GET /api/v1/ops/snapshot for GUI users (complements component-level Doctor dashboard).
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';
import { getOpsSnapshot, type OpsAggregatedSnapshot } from '@/services/opsSnapshot';
import { ActivityIcon, RefreshIcon } from '@/components/features/health/doctor-icons';

function formatUptime(seconds: number): string {
  if (seconds < 60) {
    return `${Math.floor(seconds)}s`;
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) {
    return `${h}h ${m}m`;
  }
  return `${m}m`;
}

const RuntimeOpsSnapshotCard = memo(() => {
  const t = useTranslations('settings.systemHealth.opsSnapshot');
  const [data, setData] = useState<OpsAggregatedSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const snap = await getOpsSnapshot(false);
      setData(snap);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('unreachable', { error: 'unknown' }));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Card id="runtime-ops-snapshot" className="border-border/80 bg-card/40 backdrop-blur-sm">
      <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0 pb-4">
        <div className="space-y-1">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <ActivityIcon className="w-4 h-4 text-primary" />
            {t('title')}
          </CardTitle>
          <CardDescription className="text-xs">{t('description')}</CardDescription>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
          <RefreshIcon className={cn('w-3.5 h-3.5 mr-1.5', loading && 'animate-spin')} />
          {t('refresh')}
        </Button>
      </CardHeader>
      <CardContent>
        {loading && !data ? (
          <p className="text-sm text-muted-foreground">{t('loading')}</p>
        ) : null}
        {error ? (
          <p className="text-sm text-destructive">{t('unreachable', { error })}</p>
        ) : null}
        {data ? (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
            <Metric label={t('uptime')} value={formatUptime(data.system.uptime_seconds)} />
            <Metric label={t('liveness')} value={data.liveness.state} />
            <Metric label={t('activeSessions')} value={String(data.liveness.active_sessions_count)} />
            <Metric
              label={t('memoryPressure')}
              value={`${data.resources.memory_level} (${data.resources.memory_percent.toFixed(0)}%)`}
            />
            <Metric label={t('memorySubsystem')} value={data.memory.health_status} />
            {data.doctor_summary ? (
              <Metric label={t('doctorStatus')} value={data.doctor_summary.status} />
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
});

RuntimeOpsSnapshotCard.displayName = 'RuntimeOpsSnapshotCard';

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/70 bg-muted/30 px-3 py-2.5 space-y-0.5">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="font-medium text-foreground truncate">{value}</div>
    </div>
  );
}

export default RuntimeOpsSnapshotCard;
