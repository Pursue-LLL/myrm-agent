'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconActivity,
  IconRefresh,
  IconTrash,
  IconShieldAlert,
  IconCheck,
} from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { getChannelDataPlaneStats, clearChannelDataPlane, type ChannelDataPlaneStats } from '@/services/channels';
import { toast } from 'sonner';

interface ChannelDataPlaneSectionProps {
  channel: string;
}

export function ChannelDataPlaneSection({ channel }: ChannelDataPlaneSectionProps) {
  const t = useTranslations('channels.dataPlane');
  const [stats, setStats] = useState<ChannelDataPlaneStats | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [clearing, setClearing] = useState<boolean>(false);
  const [confirmClear, setConfirmClear] = useState<boolean>(false);

  const fetchStats = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getChannelDataPlaneStats(channel);
      setStats(data);
    } catch {
      // Best-effort metrics loading
    } finally {
      setLoading(false);
    }
  }, [channel]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  const handleClear = async () => {
    if (!confirmClear) {
      setConfirmClear(true);
      return;
    }

    try {
      setClearing(true);
      const res = await clearChannelDataPlane(channel);
      toast.success(t('clearedSuccess'), {
        description: `${res.deleted_count} messages deleted`,
      });
      setConfirmClear(false);
      await fetchStats();
    } catch {
      toast.error('Failed to clear channel records');
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="rounded-xl border border-border/60 bg-card/40 p-4 sm:p-5 backdrop-blur-sm transition-all hover:border-border">
      {/* Header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between pb-3 border-b border-border/40">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <IconActivity className="h-4 w-4" />
          </div>
          <div>
            <h4 className="text-sm font-semibold text-foreground tracking-tight">{t('title')}</h4>
            <p className="text-xs text-muted-foreground">{t('description')}</p>
          </div>
        </div>

        <div className="flex items-center gap-2 self-end sm:self-auto">
          <Button
            variant="ghost"
            size="sm"
            onClick={fetchStats}
            disabled={loading}
            className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
          >
            <IconRefresh className={`h-3.5 w-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} />
            {t('refresh')}
          </Button>

          <Button
            variant={confirmClear ? 'destructive' : 'outline'}
            size="sm"
            onClick={handleClear}
            disabled={clearing || loading || (stats?.total_messages ?? 0) === 0}
            className="h-7 px-2.5 text-xs transition-colors"
          >
            <IconTrash className="h-3.5 w-3.5 mr-1" />
            {confirmClear ? t('clearConfirm') : t('clearHistory')}
          </Button>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-lg bg-muted/40 p-3 border border-border/30">
          <div className="text-xs text-muted-foreground">{t('totalMessages')}</div>
          <div className="mt-1 text-lg font-bold text-foreground tabular-nums">{stats?.total_messages ?? 0}</div>
        </div>

        <div className="rounded-lg bg-muted/40 p-3 border border-border/30">
          <div className="text-xs text-muted-foreground">{t('ambientMessages')}</div>
          <div className="mt-1 text-lg font-bold text-foreground tabular-nums">{stats?.ambient_messages ?? 0}</div>
        </div>

        <div className="rounded-lg bg-muted/40 p-3 border border-border/30">
          <div className="text-xs text-muted-foreground">{t('triggerMessages')}</div>
          <div className="mt-1 text-lg font-bold text-foreground tabular-nums">{stats?.trigger_messages ?? 0}</div>
        </div>

        <div className="rounded-lg bg-muted/40 p-3 border border-border/30">
          <div className="text-xs text-muted-foreground">{t('learningEligible')}</div>
          <div className="mt-1 text-lg font-bold text-foreground tabular-nums">{stats?.learning_eligible ?? 0}</div>
        </div>
      </div>

      {/* Badges / Security Policy Footer */}
      <div className="mt-3.5 flex flex-wrap items-center gap-2 pt-2 border-t border-border/30 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 px-2 py-0.5 text-emerald-600 dark:text-emerald-400 font-medium">
          <IconCheck className="h-3 w-3" />
          {t('secretScrubberActive')}
        </span>

        <span className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-muted-foreground">
          <IconShieldAlert className="h-3 w-3" />
          {t('retention')}: {t('retentionDays')}
        </span>
      </div>
    </div>
  );
}
