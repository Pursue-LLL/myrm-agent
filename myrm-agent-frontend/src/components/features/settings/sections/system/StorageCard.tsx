'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { IconSettings } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';

interface SubdirUsage {
  name: string;
  bytes: number;
}

interface StorageInfo {
  data_dir: string;
  disk_total_bytes: number;
  disk_used_bytes: number;
  disk_free_bytes: number;
  subdirs: SubdirUsage[];
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / 1024 ** i).toFixed(1)} ${units[i]}`;
}

const LOW_DISK_THRESHOLD = 1024 * 1024 * 1024; // 1 GB

const StorageCard = memo<{
  customDataDir?: string;
  onDataDirChange: (dir: string) => void;
}>(({ customDataDir, onDataDirChange }) => {
  const t = useTranslations('settings.system.config');
  const [storageInfo, setStorageInfo] = useState<StorageInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [isMigrating, setIsMigrating] = useState(false);

  const fetchStorageInfo = useCallback(async () => {
    try {
      const res = await fetch(`${getBackendUrl()}/api/v1/system/storage`, {
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        setStorageInfo(await res.json());
      }
    } catch {
      /* server may be offline */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchStorageInfo();
  }, [fetchStorageInfo]);

  const handleChangeDir = useCallback(async () => {
    if (!isTauriRuntime()) return;

    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({ directory: true, title: t('storageSelectDir') });
      if (!selected) return;

      const selectedDir = typeof selected === 'string' ? selected : String(selected);

      setIsMigrating(true);
      toast.info(t('storageMigrating'));

      const { invoke } = await import('@tauri-apps/api/core');
      await invoke('migrate_data_dir', { newDir: selectedDir });

      onDataDirChange(selectedDir);
      toast.success(t('storageMigrateSuccess'));
      await fetchStorageInfo();
    } catch (err) {
      toast.error(`${t('storageMigrateFailed')}: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsMigrating(false);
    }
  }, [t, onDataDirChange, fetchStorageInfo]);

  if (loading) {
    return <div className="h-32 w-full animate-pulse bg-white/5 rounded-2xl" />;
  }

  const isLowDisk = storageInfo && storageInfo.disk_free_bytes < LOW_DISK_THRESHOLD;
  const usagePercent = storageInfo
    ? Math.round((storageInfo.disk_used_bytes / storageInfo.disk_total_bytes) * 100)
    : 0;

  return (
    <section className="space-y-6">
      <div className="flex items-center gap-3 px-2">
        <IconSettings className="w-5 h-5 text-muted-foreground" />
        <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">
          {t('storageTitle')}
        </h2>
      </div>

      <div className="space-y-5 p-8 rounded-[2.5rem] bg-white/5 border border-white/10">
        {/* 当前路径 */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-4">
          <div className="space-y-1 min-w-0 flex-1">
            <label className="text-sm font-bold text-foreground">{t('storageCurrentPath')}</label>
            <p className="text-xs text-muted-foreground font-mono truncate">
              {storageInfo?.data_dir ?? customDataDir ?? '~/.myrm'}
            </p>
          </div>
          {isTauriRuntime() && (
            <button
              onClick={() => void handleChangeDir()}
              disabled={isMigrating}
              className={cn(
                'px-4 py-2 rounded-xl text-sm font-bold transition-all whitespace-nowrap',
                isMigrating
                  ? 'bg-white/5 text-muted-foreground cursor-not-allowed'
                  : 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 hover:bg-indigo-500/20',
              )}
            >
              {isMigrating ? t('storageMigrating') : t('storageChange')}
            </button>
          )}
        </div>

        {/* 磁盘使用量 */}
        {storageInfo && (
          <>
            <div className="h-px bg-white/5" />

            <div className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">
                  {t('storageUsed')}: {formatBytes(storageInfo.disk_used_bytes)}
                </span>
                <span className="text-muted-foreground">
                  {t('storageFree')}: {formatBytes(storageInfo.disk_free_bytes)}
                </span>
              </div>

              {/* 进度条 */}
              <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                <div
                  className={cn(
                    'h-full rounded-full transition-all',
                    isLowDisk ? 'bg-red-500' : usagePercent > 80 ? 'bg-amber-500' : 'bg-indigo-500',
                  )}
                  style={{ width: `${usagePercent}%` }}
                />
              </div>
            </div>

            {/* 子目录明细 */}
            {storageInfo.subdirs.length > 0 && (
              <>
                <div className="h-px bg-white/5" />
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5">
                  {storageInfo.subdirs.map((sub) => (
                    <div key={sub.name} className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground font-mono">{sub.name}</span>
                      <span className="text-foreground/70">{formatBytes(sub.bytes)}</span>
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* 低磁盘警告 */}
            {isLowDisk && (
              <>
                <div className="h-px bg-white/5" />
                <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20">
                  <p className="text-xs font-bold text-red-400">{t('storageLowWarning')}</p>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </section>
  );
});

StorageCard.displayName = 'StorageCard';

export default StorageCard;
