/**
 * [INPUT] (none)
 * [OUTPUT] BACKUP_ALERT_COMPONENT / CLOUD_SYNC_ALERT_COMPONENT: `component` of the health alert raised by repeatedly failing
 *          automatic backups (whole app / memories in the cloud);
 *          showBackupFailureToast / showCloudSyncFailureToast: localized error toast whose action opens the matching settings;
 *          BackupToastDeps: translations, router, toast and cross-tab notification capabilities they need
 * [POS] 自动备份连续失败的全局提示。服务端以 `health_alert` 事件下发（component 固定），这里不展示服务端措辞与组件名，
 *       只给本地化文案与直达对应设置的操作，落点与服务端推送深链一致：整机备份 → 「备份与恢复」，云端记忆备份 → 记忆中心「云端同步」。
 */

export const BACKUP_ALERT_COMPONENT = 'instance_backup';
export const CLOUD_SYNC_ALERT_COMPONENT = 'remote_memory_backup';

const FAILURE_TOAST_DURATION_MS = 15_000;

interface FailureToast {
  id: string;
  settingsPath: string;
  titleKey: string;
  bodyKey: string;
  actionKey: string;
}

const BACKUP_FAILURE: FailureToast = {
  id: 'instance-backup-failure',
  settingsPath: '/settings/workbench#auto-backup',
  titleKey: 'backupFailureTitle',
  bodyKey: 'backupFailureBody',
  actionKey: 'viewBackupSettings',
};

const CLOUD_SYNC_FAILURE: FailureToast = {
  id: 'remote-memory-backup-failure',
  settingsPath: '/settings/memory?sub=cloud-backup',
  titleKey: 'cloudSyncFailureTitle',
  bodyKey: 'cloudSyncFailureBody',
  actionKey: 'viewCloudSyncSettings',
};

export interface BackupToastDeps {
  t: (key: string) => string;
  router: { push: (href: string) => void };
  toast: {
    error: (
      message: string,
      options: {
        id: string;
        description: string;
        duration: number;
        dismissible: boolean;
        action: { label: string; onClick: () => void };
      },
    ) => void;
  };
  notifyIfLeader: (title: string, body: string, onClick: () => void) => void;
}

function showFailureToast(deps: BackupToastDeps, failure: FailureToast): void {
  const { t, router, toast } = deps;
  const title = t(failure.titleKey);
  const body = t(failure.bodyKey);
  const openSettings = () => router.push(failure.settingsPath);
  toast.error(title, {
    id: failure.id,
    description: body,
    duration: FAILURE_TOAST_DURATION_MS,
    dismissible: true,
    action: { label: t(failure.actionKey), onClick: openSettings },
  });
  deps.notifyIfLeader(title, body, openSettings);
}

export function showBackupFailureToast(deps: BackupToastDeps): void {
  showFailureToast(deps, BACKUP_FAILURE);
}

export function showCloudSyncFailureToast(deps: BackupToastDeps): void {
  showFailureToast(deps, CLOUD_SYNC_FAILURE);
}
