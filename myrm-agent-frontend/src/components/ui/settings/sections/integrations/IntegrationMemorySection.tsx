'use client';

import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { RefreshCw, Database, Trash2, Layers, Activity } from 'lucide-react';
import {
  getIntegrationStatus,
  syncIntegration,
  removeIntegrationTree,
  type IntegrationStatus,
  type IntegrationTreeSummary,
  type IntegrationSyncResult,
} from '@/services/integrationMemory';
import SettingsSection from '../SettingsSection';

const IntegrationMemorySection = memo(() => {
  const t = useTranslations('settings.integrationMemory');
  const [status, setStatus] = useState<IntegrationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [lastSyncResults, setLastSyncResults] = useState<IntegrationSyncResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getIntegrationStatus();
      setStatus(data);
    } catch {
      setError(t('fetchError'));
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const handleSync = useCallback(
    async (providerId?: string) => {
      try {
        setSyncing(true);
        setError(null);
        const results = await syncIntegration(providerId ? { provider_id: providerId } : {});
        setLastSyncResults(results);
        await fetchStatus();
      } catch {
        setError(t('syncError'));
      } finally {
        setSyncing(false);
      }
    },
    [t, fetchStatus],
  );

  const handleRemoveTree = useCallback(
    async (treeId: string) => {
      try {
        await removeIntegrationTree(treeId);
        await fetchStatus();
      } catch {
        setError(t('removeError'));
      }
    },
    [t, fetchStatus],
  );

  if (loading) {
    return (
      <SettingsSection title={t('title')} description={t('description')}>
        <div className="space-y-3">
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="h-16 w-full rounded-xl" />
        </div>
      </SettingsSection>
    );
  }

  const noProviders = !status || status.provider_count === 0;

  return (
    <SettingsSection title={t('title')} description={t('description')}>
      <div className="space-y-4">
        {/* Status overview */}
        <div className={cn('rounded-xl border p-4 transition-colors', 'border-border/50 bg-card/50')}>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <div
                className={cn(
                  'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
                  'bg-primary/10 text-primary',
                )}
              >
                <Database className="h-5 w-5" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground">{t('statusTitle')}</p>
                <p className="text-xs text-muted-foreground">
                  {noProviders
                    ? t('noProviders')
                    : t('statusSummary', {
                        providers: status.provider_count,
                        items: status.total_indexed_items,
                      })}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Button variant="outline" size="sm" onClick={() => fetchStatus()} disabled={loading}>
                <RefreshCw className={cn('mr-1.5 h-3.5 w-3.5', loading && 'animate-spin')} />
                {t('refresh')}
              </Button>
              {!noProviders && (
                <Button size="sm" onClick={() => handleSync()} disabled={syncing}>
                  <Activity className={cn('mr-1.5 h-3.5 w-3.5', syncing && 'animate-pulse')} />
                  {syncing ? t('syncing') : t('syncAll')}
                </Button>
              )}
            </div>
          </div>
        </div>

        {/* Error display */}
        {error && (
          <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {/* Last sync results */}
        {lastSyncResults && lastSyncResults.length > 0 && (
          <div className="rounded-lg border border-border/50 bg-card/30 p-3 space-y-2">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{t('lastSync')}</p>
            {lastSyncResults.map((r) => (
              <div key={`${r.provider}-${r.account_key}`} className="flex items-center justify-between text-sm">
                <span className="font-medium text-foreground">{r.provider}</span>
                <div className="flex items-center gap-2">
                  {r.created > 0 && (
                    <Badge variant="default" className="text-[10px] px-1.5 py-0">
                      +{r.created}
                    </Badge>
                  )}
                  {r.failed > 0 && (
                    <Badge variant="destructive" className="text-[10px] px-1.5 py-0">
                      {r.failed} {t('failed')}
                    </Badge>
                  )}
                  {r.created === 0 && r.failed === 0 && (
                    <span className="text-xs text-muted-foreground">{t('upToDate')}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Tree list */}
        {status && status.trees.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider px-1">
              {t('dataSources')}
            </p>
            {status.trees.map((tree) => (
              <TreeCard
                key={tree.tree_id}
                tree={tree}
                onSync={() => handleSync(tree.provider)}
                onRemove={() => handleRemoveTree(tree.tree_id)}
                syncing={syncing}
                t={t}
              />
            ))}
          </div>
        )}

        {/* Empty state */}
        {noProviders && (
          <div className={cn('rounded-xl border border-dashed p-8 text-center', 'border-border/50')}>
            <Layers className="mx-auto h-8 w-8 text-muted-foreground/50 mb-3" />
            <p className="text-sm font-medium text-foreground mb-1">{t('emptyTitle')}</p>
            <p className="text-xs text-muted-foreground max-w-sm mx-auto">{t('emptyDescription')}</p>
          </div>
        )}
      </div>
    </SettingsSection>
  );
});

IntegrationMemorySection.displayName = 'IntegrationMemorySection';

interface TreeCardProps {
  tree: IntegrationTreeSummary;
  onSync: () => void;
  onRemove: () => void;
  syncing: boolean;
  t: ReturnType<typeof useTranslations>;
}

const TreeCard = memo(({ tree, onSync, onRemove, syncing, t }: TreeCardProps) => {
  const [confirmRemove, setConfirmRemove] = useState(false);

  return (
    <div
      className={cn(
        'group rounded-lg border p-3 transition-all',
        'border-border/40 bg-card/30 hover:border-border/70 hover:bg-card/50',
      )}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className={cn(
              'flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-xs font-semibold uppercase',
              'bg-primary/10 text-primary',
            )}
          >
            {tree.provider.slice(0, 2)}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <p className="text-sm font-medium text-foreground truncate">{tree.provider}</p>
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0 shrink-0">
                {tree.leaf_count} {t('items')}
              </Badge>
            </div>
            {tree.root_summary && (
              <p className="text-xs text-muted-foreground truncate mt-0.5 max-w-md">{tree.root_summary}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity shrink-0">
          <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={onSync} disabled={syncing}>
            <RefreshCw className={cn('h-3 w-3', syncing && 'animate-spin')} />
          </Button>
          {confirmRemove ? (
            <Button
              variant="destructive"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={() => {
                onRemove();
                setConfirmRemove(false);
              }}
            >
              {t('confirmRemove')}
            </Button>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs text-muted-foreground hover:text-destructive"
              onClick={() => setConfirmRemove(true)}
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
});

TreeCard.displayName = 'TreeCard';

export default IntegrationMemorySection;
