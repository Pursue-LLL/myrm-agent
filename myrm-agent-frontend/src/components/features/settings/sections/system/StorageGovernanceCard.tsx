'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: i18n support)
 * - @/services/system::systemService (POS: Storage governance APIs)
 * - @/components/features/icons/PremiumIcons (POS: Standard premium UI icons)
 *
 * [OUTPUT]
 * - StorageGovernanceCard: Settings card for the user-readable space ledger of the instance's data
 *   (placeholders while measuring, the last report kept on refresh, a retryable failure notice) and
 *   point-in-time snapshot/rollback management.
 *
 * [POS]
 * Settings -> Developer Center -> Import/Export -> Storage Governance Panel.
 */

import React, { memo, useState, useEffect, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import SettingsSection from '../SettingsSection';
import { Alert, AlertDescription, AlertTitle } from '@/components/primitives/alert';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Progress } from '@/components/primitives/progress';
import { Skeleton } from '@/components/primitives/skeleton';
import {
  IconAlertCircle,
  IconDatabase,
  IconHardDrive,
  IconLoader,
  IconRotateCcw,
  IconTrash,
  IconCheck,
} from '@/components/features/icons/PremiumIcons';
import { toast } from '@/hooks/shared/useToast';
import { systemService, type StorageCategoryKey } from '@/services/system';

type StorageReport = Awaited<ReturnType<typeof systemService.getStorageGovernanceReport>>;
type LoadStatus = 'loading' | 'ready' | 'failed';

// A database category is a database file plus its log, so only directory categories have a file count worth showing.
const DATABASE_CATEGORIES: ReadonlySet<StorageCategoryKey> = new Set(['sqlite_database', 'checkpoints']);

function formatBytes(bytes: number): string {
  if (bytes <= 0) {
    return '0 B';
  }
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${units[i]}`;
}

// A failed request is explained in the user's language only: the server's own message and the exception text
// never reach the toast.
function toastFailure(title: string, description: string): void {
  toast({ title, description, variant: 'destructive' });
}

// The ledger always lists every category, so the placeholder grid has the size of the real one.
const CATEGORY_PLACEHOLDER_COUNT = 9;

// Mirrors a category tile so the grid does not jump when the first report arrives.
function CategoryTileSkeleton() {
  return (
    <div aria-hidden className="rounded-lg border border-border/30 bg-muted/20 p-3 space-y-2">
      <div className="flex items-center justify-between py-0.5">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-3 w-14" />
      </div>
      <Skeleton className="h-1.5 w-full rounded-full" />
      <div className="flex items-center justify-between py-0.5">
        <Skeleton className="h-3 w-12" />
        <Skeleton className="h-3 w-8" />
      </div>
    </div>
  );
}

// Measuring walks every file of the instance, so a failure is explained in the user's language and can be retried;
// when an earlier report is still on screen the notice says its figures may be out of date.
function LoadFailedNotice({ showsStaleReport, onRetry }: { showsStaleReport: boolean; onRetry: () => void }) {
  const t = useTranslations('settings.storageGovernance');
  const tCommon = useTranslations('common');
  return (
    <Alert variant="warning">
      <IconAlertCircle className="h-4 w-4" />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <AlertTitle>{t('loadFailedTitle')}</AlertTitle>
          <AlertDescription>{t(showsStaleReport ? 'loadFailedStaleDesc' : 'loadFailedDesc')}</AlertDescription>
        </div>
        <Button type="button" variant="secondary" size="sm" className="w-full shrink-0 sm:w-auto" onClick={onRetry}>
          {tCommon('retry')}
        </Button>
      </div>
    </Alert>
  );
}

export const StorageGovernanceCard = memo(() => {
  const t = useTranslations('settings.storageGovernance');
  const [report, setReport] = useState<StorageReport | null>(null);
  const [loadStatus, setLoadStatus] = useState<LoadStatus>('loading');
  const latestRequest = useRef(0);
  const [creatingSnapshot, setCreatingSnapshot] = useState(false);
  const [snapshotLabel, setSnapshotLabel] = useState('');
  const [restoringSnapshotId, setRestoringSnapshotId] = useState<string | null>(null);

  // The report that is already shown stays on screen while a new one is measured and after a refresh fails. Only the
  // newest request may change it: a slow earlier measurement must not overwrite a newer figure.
  const fetchReport = useCallback(async () => {
    const requestId = ++latestRequest.current;
    setLoadStatus('loading');
    try {
      const next = await systemService.getStorageGovernanceReport();
      if (requestId !== latestRequest.current) {
        return;
      }
      setReport(next);
      setLoadStatus('ready');
    } catch {
      if (requestId === latestRequest.current) {
        setLoadStatus('failed');
      }
    }
  }, []);

  useEffect(() => {
    void fetchReport();
    return () => {
      latestRequest.current += 1;
    };
  }, [fetchReport]);

  const handleCreateSnapshot = useCallback(async () => {
    if (!snapshotLabel.trim()) {
      return;
    }
    setCreatingSnapshot(true);
    try {
      const res = await systemService.createStateSnapshot(snapshotLabel.trim());
      if (res.success) {
        toast({
          title: t('snapshotSuccessTitle'),
          description: t('snapshotSuccessDesc'),
        });
        setSnapshotLabel('');
        await fetchReport();
      } else {
        toastFailure(t('snapshotFailedTitle'), t('snapshotFailedDesc'));
      }
    } catch {
      toastFailure(t('snapshotFailedTitle'), t('snapshotFailedDesc'));
    } finally {
      setCreatingSnapshot(false);
    }
  }, [fetchReport, snapshotLabel, t]);

  const handleRestoreSnapshot = useCallback(
    async (snapshotId: string) => {
      setRestoringSnapshotId(snapshotId);
      try {
        const res = await systemService.restoreStateSnapshot(snapshotId);
        if (res.success) {
          toast({
            title: t('restoreSuccessTitle'),
            description: t('restoreSuccessDesc'),
          });
          await fetchReport();
        } else {
          toastFailure(t('restoreFailedTitle'), t('restoreFailedDesc'));
        }
      } catch {
        toastFailure(t('restoreFailedTitle'), t('restoreFailedDesc'));
      } finally {
        setRestoringSnapshotId(null);
      }
    },
    [fetchReport, t],
  );

  const handleDeleteSnapshot = useCallback(
    async (snapshotId: string) => {
      try {
        const res = await systemService.deleteStateSnapshot(snapshotId);
        if (res.success) {
          toast({
            title: t('deleteSuccessTitle'),
            description: t('deleteSuccessDesc'),
          });
          await fetchReport();
        } else {
          toastFailure(t('deleteFailedTitle'), t('deleteFailedDesc'));
        }
      } catch {
        toastFailure(t('deleteFailedTitle'), t('deleteFailedDesc'));
      }
    },
    [fetchReport, t],
  );

  // Without a report there is nothing to show once measuring failed; the notice carries the retry instead.
  const showLedger = report !== null || loadStatus === 'loading';

  return (
    <SettingsSection title={t('title')} description={t('description')}>
      <div className="space-y-6">
        {loadStatus === 'failed' && (
          <LoadFailedNotice showsStaleReport={report !== null} onRetry={() => void fetchReport()} />
        )}
        {showLedger && (
          <>
            {/* Total Usage & Disk Overview */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="rounded-xl border border-border/40 bg-background/50 p-4 space-y-2 flex flex-col justify-center">
                <div className="flex items-center gap-2 text-xs text-muted-foreground font-medium">
                  <IconDatabase className="w-4 h-4 text-primary" />
                  {t('totalAgentStateSize')}
                </div>
                <div className="text-2xl font-bold tracking-tight">
                  {report ? formatBytes(report.total_storage_bytes) : <Skeleton className="h-8 w-28" />}
                </div>
              </div>

              <div className="rounded-xl border border-border/40 bg-background/50 p-4 space-y-2 md:col-span-2">
                <div className="flex items-center justify-between text-xs text-muted-foreground font-medium">
                  <span className="inline-flex items-center gap-2">
                    <IconHardDrive className="w-4 h-4 text-primary" />
                    {t('diskSpaceOverview')}
                  </span>
                  {report ? <span>{`${report.disk_used_percentage}%`}</span> : <Skeleton className="h-3.5 w-8" />}
                </div>
                <Progress value={report?.disk_used_percentage ?? 0} className="h-2" />
                <div className="flex justify-between text-xs text-muted-foreground">
                  {report ? (
                    <>
                      <span>{t('freeDisk', { free: formatBytes(report.disk_free_bytes) })}</span>
                      <span>{t('totalDisk', { total: formatBytes(report.disk_total_bytes) })}</span>
                    </>
                  ) : (
                    <>
                      <Skeleton className="my-0.5 h-3 w-24" />
                      <Skeleton className="my-0.5 h-3 w-24" />
                    </>
                  )}
                </div>
              </div>
            </div>

            {/* Breakdown by Category */}
            <div className="space-y-3">
              <h4 className="text-sm font-semibold">{t('categoriesBreakdown')}</h4>

              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                {report?.categories.map((cat) => (
                  <div
                    key={cat.category}
                    className="rounded-lg border border-border/30 bg-muted/20 p-3 flex flex-col justify-between space-y-2"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-foreground truncate">
                        {t(`categories.${cat.category}`)}
                      </span>
                      <span className="text-xs font-semibold">{formatBytes(cat.bytes)}</span>
                    </div>
                    <div className="w-full bg-border/40 h-1.5 rounded-full overflow-hidden">
                      <div
                        className="bg-primary h-full transition-all"
                        style={{ width: `${Math.min(100, Math.max(1, cat.percentage))}%` }}
                      />
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                      <span>
                        {DATABASE_CATEGORIES.has(cat.category) ? '' : t('filesCount', { count: cat.item_count })}
                      </span>
                      <span>{cat.percentage.toFixed(1)}%</span>
                    </div>
                  </div>
                ))}
                {!report &&
                  Array.from({ length: CATEGORY_PLACEHOLDER_COUNT }, (_, index) => (
                    <CategoryTileSkeleton key={index} />
                  ))}
              </div>
            </div>
          </>
        )}

        {/* Snapshots & Rollback */}
        <div className="space-y-3 pt-2 border-t border-border/30">
          <h4 className="text-sm font-semibold">{t('snapshotsAndRollback')}</h4>
          <p className="text-xs text-muted-foreground">{t('snapshotsDesc')}</p>

          <div className="flex items-center gap-2">
            <Input
              placeholder={t('snapshotLabelPlaceholder')}
              value={snapshotLabel}
              onChange={(e) => setSnapshotLabel(e.target.value)}
              className="h-8 text-xs flex-1"
            />
            <Button
              size="sm"
              onClick={handleCreateSnapshot}
              disabled={creatingSnapshot || !snapshotLabel.trim()}
              className="h-8 text-xs gap-1"
            >
              {creatingSnapshot ? (
                <IconLoader className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <IconCheck className="w-3.5 h-3.5" />
              )}
              {t('createSnapshot')}
            </Button>
          </div>

          {report?.snapshots && report.snapshots.length > 0 && (
            <div className="rounded-lg border border-border/30 divide-y divide-border/20 max-h-48 overflow-y-auto">
              {report.snapshots.map((snap) => (
                <div key={snap.snapshot_id} className="p-2.5 flex items-center justify-between text-xs">
                  <div className="space-y-0.5">
                    <div className="font-medium text-foreground">{snap.label}</div>
                    <div className="text-[11px] text-muted-foreground flex items-center gap-2">
                      <span>{formatBytes(snap.size_bytes)}</span>
                      <span>•</span>
                      <span>{new Date(snap.created_at).toLocaleString()}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRestoreSnapshot(snap.snapshot_id)}
                      disabled={restoringSnapshotId === snap.snapshot_id}
                      className="h-7 text-xs px-2 gap-1 text-primary hover:text-primary"
                    >
                      {restoringSnapshotId === snap.snapshot_id ? (
                        <IconLoader className="w-3 h-3 animate-spin" />
                      ) : (
                        <IconRotateCcw className="w-3 h-3" />
                      )}
                      {t('restore')}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDeleteSnapshot(snap.snapshot_id)}
                      aria-label={t('deleteSnapshot')}
                      className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                    >
                      <IconTrash className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </SettingsSection>
  );
});

StorageGovernanceCard.displayName = 'StorageGovernanceCard';
