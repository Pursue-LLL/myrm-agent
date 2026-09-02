'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: i18n support)
 * - @/services/system::systemService (POS: Storage governance & compaction APIs)
 * - @/components/features/icons/PremiumIcons (POS: Standard premium UI icons)
 *
 * [OUTPUT]
 * - StorageGovernanceCard: Settings card for user-readable database/storage decomposition,
 *   compaction triggers, and point-in-time snapshot/rollback management.
 *
 * [POS]
 * Settings -> Developer Center -> Import/Export -> Storage Governance Panel.
 */

import React, { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import SettingsSection from '../SettingsSection';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Progress } from '@/components/primitives/progress';
import {
  IconDatabase,
  IconHardDrive,
  IconLoader,
  IconRotateCcw,
  IconShieldCheck,
  IconTrash,
  IconWrench,
  IconCheck,
} from '@/components/features/icons/PremiumIcons';
import { toast } from '@/hooks/shared/useToast';
import { systemService } from '@/services/system';

type StorageReport = Awaited<ReturnType<typeof systemService.getStorageGovernanceReport>>;

function formatBytes(bytes: number): string {
  if (bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${units[i]}`;
}

export const StorageGovernanceCard = memo(() => {
  const t = useTranslations('settings.storageGovernance');
  const [report, setReport] = useState<StorageReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [compacting, setCompacting] = useState(false);
  const [creatingSnapshot, setCreatingSnapshot] = useState(false);
  const [snapshotLabel, setSnapshotLabel] = useState('');
  const [restoringSnapshotId, setRestoringSnapshotId] = useState<string | null>(null);

  const fetchReport = useCallback(async () => {
    try {
      setLoading(true);
      const data = await systemService.getStorageGovernanceReport();
      setReport(data);
    } catch {
      // Graceful fallback
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchReport();
  }, [fetchReport]);

  const handleCompact = useCallback(async () => {
    setCompacting(true);
    try {
      const res = await systemService.executeStorageCompaction();
      if (res.success) {
        toast({
          title: t('compactionSuccessTitle'),
          description: t('compactionSuccessDesc', { freed: formatBytes(res.freed_bytes) }),
        });
        await fetchReport();
      } else {
        toast({
          title: t('compactionFailedTitle'),
          description: res.message,
          variant: 'destructive',
        });
      }
    } catch (err) {
      toast({
        title: t('compactionFailedTitle'),
        description: err instanceof Error ? err.message : String(err),
        variant: 'destructive',
      });
    } finally {
      setCompacting(false);
    }
  }, [fetchReport, t]);

  const handleCreateSnapshot = useCallback(async () => {
    if (!snapshotLabel.trim()) return;
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
        toast({
          title: t('snapshotFailedTitle'),
          description: res.message,
          variant: 'destructive',
        });
      }
    } catch (err) {
      toast({
        title: t('snapshotFailedTitle'),
        description: err instanceof Error ? err.message : String(err),
        variant: 'destructive',
      });
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
          toast({
            title: t('restoreFailedTitle'),
            description: res.message,
            variant: 'destructive',
          });
        }
      } catch (err) {
        toast({
          title: t('restoreFailedTitle'),
          description: err instanceof Error ? err.message : String(err),
          variant: 'destructive',
        });
      } finally {
        setRestoringSnapshotId(null);
      }
    },
    [fetchReport, t]
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
        }
      } catch (err) {
        toast({
          title: t('deleteFailedTitle'),
          description: err instanceof Error ? err.message : String(err),
          variant: 'destructive',
        });
      }
    },
    [fetchReport, t]
  );

  return (
    <SettingsSection
      title={t('title')}
      description={t('description')}
    >
      <div className="space-y-6">
        {/* Total Usage & Disk Overview */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="rounded-xl border border-border/40 bg-background/50 p-4 space-y-2">
            <div className="flex items-center gap-2 text-xs text-muted-foreground font-medium">
              <IconDatabase className="w-4 h-4 text-primary" />
              {t('totalAgentStateSize')}
            </div>
            <div className="text-2xl font-bold tracking-tight">
              {report ? formatBytes(report.total_storage_bytes) : '...'}
            </div>
            <div className="text-xs text-muted-foreground">
              {report?.is_growth_healthy ? (
                <span className="text-emerald-500 font-medium inline-flex items-center gap-1">
                  <IconShieldCheck className="w-3.5 h-3.5" />
                  {t('healthyGrowth')}
                </span>
              ) : (
                <span className="text-amber-500 font-medium">{t('growthWarning')}</span>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-border/40 bg-background/50 p-4 space-y-2 md:col-span-2">
            <div className="flex items-center justify-between text-xs text-muted-foreground font-medium">
              <span className="inline-flex items-center gap-2">
                <IconHardDrive className="w-4 h-4 text-sky-500" />
                {t('diskSpaceOverview')}
              </span>
              <span>{report ? `${report.disk_used_percentage}%` : '...'}</span>
            </div>
            <Progress value={report?.disk_used_percentage ?? 0} className="h-2" />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{report ? t('freeDisk', { free: formatBytes(report.disk_free_bytes) }) : ''}</span>
              <span>{report ? t('totalDisk', { total: formatBytes(report.disk_total_bytes) }) : ''}</span>
            </div>
          </div>
        </div>

        {/* Breakdown by Category */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold">{t('categoriesBreakdown')}</h4>
            <Button
              variant="outline"
              size="sm"
              onClick={handleCompact}
              disabled={compacting || loading}
              className="gap-1.5 text-xs h-8"
            >
              {compacting ? <IconLoader className="w-3.5 h-3.5 animate-spin" /> : <IconWrench className="w-3.5 h-3.5" />}
              {t('compactAndPurge')}
            </Button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
            {report?.categories.map((cat) => (
              <div
                key={cat.category}
                className="rounded-lg border border-border/30 bg-muted/20 p-3 flex flex-col justify-between space-y-2"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-foreground truncate">{cat.display_name}</span>
                  <span className="text-xs font-semibold">{formatBytes(cat.bytes)}</span>
                </div>
                <div className="w-full bg-border/40 h-1.5 rounded-full overflow-hidden">
                  <div className="bg-primary h-full transition-all" style={{ width: `${Math.min(100, Math.max(1, cat.percentage))}%` }} />
                </div>
                <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                  <span>{t('itemsCount', { count: cat.item_count })}</span>
                  <span>{cat.percentage.toFixed(1)}%</span>
                </div>
              </div>
            ))}
          </div>
        </div>

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
              {creatingSnapshot ? <IconLoader className="w-3.5 h-3.5 animate-spin" /> : <IconCheck className="w-3.5 h-3.5" />}
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
