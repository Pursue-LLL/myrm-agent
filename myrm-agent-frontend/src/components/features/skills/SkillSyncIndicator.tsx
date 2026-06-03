'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { toast } from '@/hooks/useToast';
import { getSkillSyncStatus, triggerSkillSync, type SkillSyncStatus } from '@/services/skill';
import { cn } from '@/lib/utils';

const SkillSyncIndicator = memo(() => {
  const t = useTranslations('settings.skills.sync');
  const [status, setStatus] = useState<SkillSyncStatus | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getSkillSyncStatus();
      setStatus(data);
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 30_000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const handleSync = useCallback(async () => {
    if (isSyncing) return;
    setIsSyncing(true);
    try {
      const result = await triggerSkillSync();
      if (result.success) {
        toast({
          title: t('syncSuccess', {
            push: result.push_count,
            pull: result.pull_new + result.pull_updated,
          }),
        });
      } else if (result.error) {
        toast({ title: t('syncFailed', { error: result.error }), variant: 'destructive' });
      }
      await fetchStatus();
    } catch {
      toast({ title: t('syncFailed', { error: 'Network error' }), variant: 'destructive' });
    } finally {
      setIsSyncing(false);
    }
  }, [isSyncing, fetchStatus, t]);

  if (!status?.enabled) return null;

  const hasPending = status.pending_push_count > 0 || status.pending_pull_count > 0;

  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <div
        className={cn(
          'h-2 w-2 rounded-full',
          status.is_syncing || isSyncing ? 'bg-amber-400 animate-pulse' : hasPending ? 'bg-blue-400' : 'bg-emerald-400',
        )}
      />
      <span className="hidden sm:inline">
        {status.is_syncing || isSyncing
          ? t('syncing')
          : status.last_sync_at
            ? t('lastSync', { time: new Date(status.last_sync_at).toLocaleString() })
            : t('neverSynced')}
      </span>
      {hasPending && (
        <span className="text-blue-500">
          {status.pending_pull_count > 0 && t('pendingPull', { count: status.pending_pull_count })}
        </span>
      )}
      <Button
        variant="ghost"
        size="sm"
        className="h-6 px-2 text-xs"
        onClick={handleSync}
        disabled={isSyncing || status.is_syncing}
      >
        {t('triggerSync')}
      </Button>
    </div>
  );
});

SkillSyncIndicator.displayName = 'SkillSyncIndicator';

export default SkillSyncIndicator;
