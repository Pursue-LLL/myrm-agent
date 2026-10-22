/**
 * [INPUT] (none)
 * [OUTPUT] BACKUP_ALERT_COMPONENT: `component` of the health alert raised by repeatedly failing automatic backups;
 *          showBackupFailureToast: localized error toast whose action opens the backup settings;
 *          BackupToastDeps: translations, router, toast and cross-tab notification capabilities it needs
 * [POS] 自动备份连续失败的全局提示。服务端以 `health_alert` 事件下发（component 固定），这里不展示服务端措辞与组件名，
 *       只给本地化文案与直达「备份与恢复」设置的操作，落点与服务端推送深链一致。
 */

export const BACKUP_ALERT_COMPONENT = 'instance_backup';

const BACKUP_SETTINGS_PATH = '/settings/workbench#auto-backup';
const BACKUP_TOAST_ID = 'instance-backup-failure';
const BACKUP_TOAST_DURATION_MS = 15_000;

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

export function showBackupFailureToast(deps: BackupToastDeps): void {
  const { t, router, toast } = deps;
  const title = t('backupFailureTitle');
  const body = t('backupFailureBody');
  const openSettings = () => router.push(BACKUP_SETTINGS_PATH);
  toast.error(title, {
    id: BACKUP_TOAST_ID,
    description: body,
    duration: BACKUP_TOAST_DURATION_MS,
    dismissible: true,
    action: { label: t('viewBackupSettings'), onClick: openSettings },
  });
  deps.notifyIfLeader(title, body, openSettings);
}
