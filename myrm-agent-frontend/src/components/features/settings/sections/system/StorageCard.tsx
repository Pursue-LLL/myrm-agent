'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  Database,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Layers,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { IconSettings } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';
import {
  systemService,
  type StorageOptimizePreflightResponse,
  type StorageOptimizeResponse,
} from '@/services/system';

interface SubdirUsage {
  name: string;
  bytes: number;
}

interface DatabaseStorageBreakdown {
  main_db_bytes: number;
  wal_bytes: number;
  shm_bytes: number;
  total_bytes: number;
}

interface StorageInfo {
  data_dir: string;
  disk_total_bytes: number;
  disk_used_bytes: number;
  disk_free_bytes: number;
  subdirs: SubdirUsage[];
  db_breakdown?: DatabaseStorageBreakdown;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) {
    return '0 B';
  }
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

  // Storage Optimization States
  const [showOptimizePanel, setShowOptimizePanel] = useState(false);
  const [isPreflighting, setIsPreflighting] = useState(false);
  const [preflight, setPreflight] = useState<StorageOptimizePreflightResponse | null>(null);
  const [selectedMode, setSelectedMode] = useState<'deep' | 'light'>('deep');
  const [isOptimizing, setIsOptimizing] = useState(false);
  const [optimizeResult, setOptimizeResult] = useState<StorageOptimizeResponse | null>(null);

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
    if (!isTauriRuntime()) {
      return;
    }

    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({ directory: true, title: t('storageSelectDir') });
      if (!selected) {
        return;
      }

      const selectedDir = typeof selected === 'string' ? selected : String(selected);

      setIsMigrating(true);
      toast.info(t('storageMigrating'));

      const { invoke } = await import('@tauri-apps/api/core');
      const actionTicket = await invoke<string>('issue_sensitive_action_ticket', { action: 'migrate_data_dir' });
      await invoke('migrate_data_dir', { newDir: selectedDir, actionTicket });

      onDataDirChange(selectedDir);
      toast.success(t('storageMigrateSuccess'));
      await fetchStorageInfo();
    } catch (err) {
      toast.error(`${t('storageMigrateFailed')}: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsMigrating(false);
    }
  }, [t, onDataDirChange, fetchStorageInfo]);

  // Handle open optimize panel & trigger preflight check
  const handleToggleOptimize = useCallback(async () => {
    if (showOptimizePanel) {
      setShowOptimizePanel(false);
      return;
    }

    setShowOptimizePanel(true);
    setIsPreflighting(true);
    setOptimizeResult(null);
    try {
      const data = await systemService.getStorageOptimizePreflight();
      setPreflight(data);
      setSelectedMode(data.recommended_mode);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('storageOptimizeFailed'));
    } finally {
      setIsPreflighting(false);
    }
  }, [showOptimizePanel, t]);

  // Execute optimization
  const handleExecuteOptimize = useCallback(async () => {
    setIsOptimizing(true);
    setOptimizeResult(null);
    try {
      const res = await systemService.executeStorageOptimize({
        mode: selectedMode,
        create_backup: true,
      });
      setOptimizeResult(res);
      if (res.reclaimed_bytes > 0) {
        toast.success(
          t('storageOptimizeSuccess', {
            reclaimed: formatBytes(res.reclaimed_bytes),
            percentage: res.reclaimed_percentage,
          }),
        );
      } else {
        toast.info(t('storageOptimizeNoReclaim'));
      }
      await fetchStorageInfo();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('storageOptimizeFailed'));
    } finally {
      setIsOptimizing(false);
    }
  }, [selectedMode, t, fetchStorageInfo]);

  if (loading) {
    return <div className="h-32 w-full animate-pulse bg-white/5 rounded-2xl" />;
  }

  const isLowDisk = storageInfo && storageInfo.disk_free_bytes < LOW_DISK_THRESHOLD;
  const usagePercent = storageInfo ? Math.round((storageInfo.disk_used_bytes / storageInfo.disk_total_bytes) * 100) : 0;
  const dbSubdir = storageInfo?.subdirs.find((s) => s.name === 'data.db');

  return (
    <section className="space-y-6">
      <div className="flex items-center gap-3 px-2">
        <IconSettings className="w-5 h-5 text-muted-foreground" />
        <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">{t('storageTitle')}</h2>
      </div>

      <div className="space-y-5 p-6 sm:p-8 rounded-[2.5rem] bg-white/5 border border-white/10">
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
                <div className="space-y-3">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5">
                    {storageInfo.subdirs.map((sub) => (
                      <div key={sub.name} className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground font-mono">{sub.name}</span>
                        <span className="text-foreground/70">{formatBytes(sub.bytes)}</span>
                      </div>
                    ))}
                  </div>

                  {/* 数据库存储优化入口 */}
                  {dbSubdir && (
                    <div className="pt-2">
                      <button
                        type="button"
                        onClick={() => void handleToggleOptimize()}
                        disabled={isOptimizing}
                        className={cn(
                          'w-full flex items-center justify-between p-3 rounded-2xl border transition-all text-left',
                          showOptimizePanel
                            ? 'bg-indigo-500/10 border-indigo-500/30 text-indigo-300'
                            : 'bg-white/[0.03] border-white/10 hover:bg-white/[0.06] text-foreground',
                        )}
                      >
                        <div className="flex items-center gap-2.5">
                          <Database className="w-4 h-4 text-indigo-400" />
                          <span className="text-xs font-bold">{t('storageOptimizeTitle')}</span>
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 font-mono">
                            {formatBytes(dbSubdir.bytes)}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                          <span>{showOptimizePanel ? t('storageOptimize') : t('storageOptimize')}</span>
                          {showOptimizePanel ? (
                            <ChevronUp className="w-3.5 h-3.5" />
                          ) : (
                            <ChevronDown className="w-3.5 h-3.5" />
                          )}
                        </div>
                      </button>

                      {/* 展开的存储优化面板 */}
                      {showOptimizePanel && (
                        <div className="mt-3 p-4 rounded-2xl bg-black/20 border border-white/10 space-y-4">
                          <div className="text-xs text-muted-foreground leading-relaxed">
                            {t('storageOptimizeDesc')}
                          </div>

                          {isPreflighting ? (
                            <div className="flex items-center gap-2 text-xs text-indigo-400 py-2">
                              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                              <span>{t('storageOptimizePreflightLoading')}</span>
                            </div>
                          ) : preflight ? (
                            <div className="space-y-3">
                              {/* 三元组分解数据 */}
                              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 p-2.5 rounded-xl bg-white/[0.02] border border-white/5 text-[11px]">
                                <div>
                                  <span className="text-muted-foreground">{t('storageOptimizeBreakdownMain')}: </span>
                                  <span className="font-mono text-foreground font-semibold">
                                    {formatBytes(preflight.db_breakdown.main_db_bytes)}
                                  </span>
                                </div>
                                <div>
                                  <span className="text-muted-foreground">{t('storageOptimizeBreakdownWal')}: </span>
                                  <span className="font-mono text-foreground font-semibold">
                                    {formatBytes(preflight.db_breakdown.wal_bytes)}
                                  </span>
                                </div>
                                <div>
                                  <span className="text-muted-foreground">{t('storageOptimizeBreakdownShm')}: </span>
                                  <span className="font-mono text-foreground font-semibold">
                                    {formatBytes(preflight.db_breakdown.shm_bytes)}
                                  </span>
                                </div>
                              </div>

                              {/* 活跃后台任务安全拦截提示 */}
                              {!preflight.is_safe_to_optimize && (
                                <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-start gap-2.5 text-xs text-amber-300">
                                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                                  <span>{preflight.reason || t('storageOptimizeActiveJobsWarning')}</span>
                                </div>
                              )}

                              {/* 模式选择 */}
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                                <button
                                  type="button"
                                  onClick={() => setSelectedMode('deep')}
                                  disabled={!preflight.can_deep_optimize || isOptimizing}
                                  className={cn(
                                    'p-3 rounded-xl border text-left transition-all space-y-1',
                                    selectedMode === 'deep'
                                      ? 'bg-indigo-500/20 border-indigo-500/40 text-foreground ring-1 ring-indigo-500/30'
                                      : 'bg-white/[0.02] border-white/5 text-muted-foreground hover:bg-white/[0.04]',
                                    !preflight.can_deep_optimize && 'opacity-50 cursor-not-allowed',
                                  )}
                                >
                                  <div className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                                    <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                                    <span>{t('storageOptimizeModeDeep')}</span>
                                  </div>
                                  <p className="text-[11px] text-muted-foreground leading-normal">
                                    {t('storageOptimizeModeDeepDesc')}
                                  </p>
                                </button>

                                <button
                                  type="button"
                                  onClick={() => setSelectedMode('light')}
                                  disabled={isOptimizing}
                                  className={cn(
                                    'p-3 rounded-xl border text-left transition-all space-y-1',
                                    selectedMode === 'light'
                                      ? 'bg-indigo-500/20 border-indigo-500/40 text-foreground ring-1 ring-indigo-500/30'
                                      : 'bg-white/[0.02] border-white/5 text-muted-foreground hover:bg-white/[0.04]',
                                  )}
                                >
                                  <div className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                                    <Layers className="w-3.5 h-3.5 text-emerald-400" />
                                    <span>{t('storageOptimizeModeLight')}</span>
                                  </div>
                                  <p className="text-[11px] text-muted-foreground leading-normal">
                                    {t('storageOptimizeModeLightDesc')}
                                  </p>
                                </button>
                              </div>

                              {/* 操作按钮区 */}
                              <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-2">
                                <span className="text-[11px] text-muted-foreground/80">
                                  {t('storageOptimizeBackupNote')}
                                </span>
                                <button
                                  type="button"
                                  onClick={() => void handleExecuteOptimize()}
                                  disabled={!preflight.is_safe_to_optimize || isOptimizing}
                                  className={cn(
                                    'w-full sm:w-auto px-5 py-2 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2',
                                    !preflight.is_safe_to_optimize || isOptimizing
                                      ? 'bg-white/5 text-muted-foreground cursor-not-allowed'
                                      : 'bg-indigo-500 text-white hover:bg-indigo-600 shadow-lg shadow-indigo-500/20',
                                  )}
                                >
                                  {isOptimizing ? (
                                    <>
                                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                                      <span>{t('storageOptimizing')}</span>
                                    </>
                                  ) : (
                                    <>
                                      <Sparkles className="w-3.5 h-3.5" />
                                      <span>{t('storageOptimize')}</span>
                                    </>
                                  )}
                                </button>
                              </div>

                              {/* 优化结果提示 */}
                              {optimizeResult && (
                                <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-start gap-2.5 text-xs text-emerald-300">
                                  <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5 text-emerald-400" />
                                  <div className="space-y-0.5">
                                    <div className="font-bold">
                                      {optimizeResult.reclaimed_bytes > 0
                                        ? t('storageOptimizeSuccess', {
                                            reclaimed: formatBytes(optimizeResult.reclaimed_bytes),
                                            percentage: optimizeResult.reclaimed_percentage,
                                          })
                                        : t('storageOptimizeNoReclaim')}
                                    </div>
                                    <div className="text-[11px] opacity-80">
                                      {optimizeResult.message}
                                    </div>
                                  </div>
                                </div>
                              )}
                            </div>
                          ) : null}
                        </div>
                      )}
                    </div>
                  )}
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
