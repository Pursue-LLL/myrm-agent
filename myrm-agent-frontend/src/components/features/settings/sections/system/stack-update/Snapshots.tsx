'use client';

import { useTranslations } from 'next-intl';
import { QueuedRestartNotice } from '@/components/features/instance-archive/QueuedRestartNotice';
import { cn } from '@/lib/utils/classnameUtils';

/** 更新前的本地快照：自动备份开关、手动备份、恢复与删除。 */

export interface StackSnapshotItem {
  snapshot_id: string;
  label: string;
  size_bytes: number;
  created_at: string;
  from_version?: string | null;
  to_version?: string | null;
}

interface StackUpdateSnapshotsProps {
  snapshots: StackSnapshotItem[];
  autoBackupEnabled: boolean;
  backupBusy: boolean;
  backupError: boolean;
  restoredId: string | null;
  onToggleAutoBackup: () => void;
  onBackupNow: () => void;
  onRestore: (snapshotId: string) => void;
  onDelete: (snapshotId: string) => void;
}

export default function StackUpdateSnapshots({
  snapshots,
  autoBackupEnabled,
  backupBusy,
  backupError,
  restoredId,
  onToggleAutoBackup,
  onBackupNow,
  onRestore,
  onDelete,
}: StackUpdateSnapshotsProps) {
  const t = useTranslations('settings.system.stackUpdate');

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">{t('backupTitle')}</p>
        <button
          type="button"
          role="switch"
          aria-checked={autoBackupEnabled}
          onClick={onToggleAutoBackup}
          className={cn(
            'px-3 py-1.5 rounded-lg border text-xs font-bold transition-colors',
            autoBackupEnabled
              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400'
              : 'border-white/10 text-muted-foreground hover:bg-white/5',
          )}
        >
          {t('backupAuto')}
        </button>
        <button
          type="button"
          onClick={onBackupNow}
          disabled={backupBusy}
          className="px-3 py-1.5 rounded-lg border border-white/10 text-xs font-bold hover:bg-white/5 transition-colors disabled:opacity-50"
        >
          {t('backupNow')}
        </button>
      </div>
      {backupError && (
        <div className="space-y-1">
          <p className="text-xs text-destructive-text">{t('backupFailed')}</p>
          <p className="text-xs text-muted-foreground leading-relaxed">{t('backupManualGuide')}</p>
        </div>
      )}
      {restoredId && (
        <div className="space-y-2">
          <p className="text-xs text-emerald-400">
            {t('restoreDone')} {t('restartRequired')}
          </p>
          <QueuedRestartNotice />
        </div>
      )}
      {snapshots.length === 0 && <p className="text-xs text-muted-foreground">{t('snapshotEmpty')}</p>}
      {snapshots.length > 0 && (
        <ul className="space-y-1">
          {snapshots.slice(0, 5).map((snapshot) => (
            <li key={snapshot.snapshot_id} className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">{snapshot.label}</span>
              <span>
                {(snapshot.size_bytes / 1024).toFixed(0)} KB · {snapshot.created_at.slice(0, 10)}
              </span>
              <button
                type="button"
                onClick={() => onRestore(snapshot.snapshot_id)}
                disabled={backupBusy}
                className="px-2 py-1 rounded-lg border border-white/10 font-bold hover:bg-white/5 transition-colors disabled:opacity-50"
              >
                {t('snapshotRestore')}
              </button>
              <button
                type="button"
                onClick={() => onDelete(snapshot.snapshot_id)}
                disabled={backupBusy}
                className="px-2 py-1 rounded-lg border border-white/10 hover:bg-white/5 transition-colors disabled:opacity-50"
              >
                {t('snapshotDelete')}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
