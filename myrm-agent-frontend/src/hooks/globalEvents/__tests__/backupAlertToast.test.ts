import { describe, expect, it, vi } from 'vitest';

import {
  BACKUP_ALERT_COMPONENT,
  CLOUD_SYNC_ALERT_COMPONENT,
  showBackupFailureToast,
  showCloudSyncFailureToast,
  type BackupToastDeps,
} from '@/hooks/globalEvents/backupAlertToast';

function buildDeps() {
  const error = vi.fn();
  const push = vi.fn();
  const notifyIfLeader = vi.fn();
  const deps: BackupToastDeps = { t: (key) => key, router: { push }, toast: { error }, notifyIfLeader };
  return { deps, error, push, notifyIfLeader };
}

describe('showBackupFailureToast', () => {
  it('matches the component the server raises the alert for', () => {
    expect(BACKUP_ALERT_COMPONENT).toBe('instance_backup');
  });

  it('shows localized copy only, with a single replaceable toast', () => {
    const { deps, error } = buildDeps();

    showBackupFailureToast(deps);

    expect(error).toHaveBeenCalledOnce();
    expect(error).toHaveBeenCalledWith(
      'backupFailureTitle',
      expect.objectContaining({
        id: 'instance-backup-failure',
        description: 'backupFailureBody',
        duration: 15_000,
        dismissible: true,
      }),
    );
  });

  it('opens the backup settings from the toast and from the cross-tab notification', () => {
    const { deps, error, push, notifyIfLeader } = buildDeps();

    showBackupFailureToast(deps);
    const options = error.mock.calls[0][1] as { action: { label: string; onClick: () => void } };
    expect(options.action.label).toBe('viewBackupSettings');
    options.action.onClick();
    expect(push).toHaveBeenLastCalledWith('/settings/workbench#auto-backup');

    expect(notifyIfLeader).toHaveBeenCalledWith('backupFailureTitle', 'backupFailureBody', expect.any(Function));
    (notifyIfLeader.mock.calls[0][2] as () => void)();
    expect(push).toHaveBeenCalledTimes(2);
    expect(push).toHaveBeenLastCalledWith('/settings/workbench#auto-backup');
  });
});

describe('showCloudSyncFailureToast', () => {
  it('matches the component the server raises the alert for', () => {
    expect(CLOUD_SYNC_ALERT_COMPONENT).toBe('remote_memory_backup');
  });

  it('shows localized copy only, as its own replaceable toast', () => {
    const { deps, error } = buildDeps();

    showCloudSyncFailureToast(deps);

    expect(error).toHaveBeenCalledOnce();
    expect(error).toHaveBeenCalledWith(
      'cloudSyncFailureTitle',
      expect.objectContaining({
        id: 'remote-memory-backup-failure',
        description: 'cloudSyncFailureBody',
        duration: 15_000,
        dismissible: true,
      }),
    );
  });

  it('opens the cloud backup settings from the toast and from the cross-tab notification', () => {
    const { deps, error, push, notifyIfLeader } = buildDeps();

    showCloudSyncFailureToast(deps);
    const options = error.mock.calls[0][1] as { action: { label: string; onClick: () => void } };
    expect(options.action.label).toBe('viewCloudSyncSettings');
    options.action.onClick();
    expect(push).toHaveBeenLastCalledWith('/settings/memory?sub=cloud-backup');

    expect(notifyIfLeader).toHaveBeenCalledWith('cloudSyncFailureTitle', 'cloudSyncFailureBody', expect.any(Function));
    (notifyIfLeader.mock.calls[0][2] as () => void)();
    expect(push).toHaveBeenCalledTimes(2);
    expect(push).toHaveBeenLastCalledWith('/settings/memory?sub=cloud-backup');
  });

  it('never replaces the toast of the whole-app backup', () => {
    const { deps, error } = buildDeps();

    showBackupFailureToast(deps);
    showCloudSyncFailureToast(deps);

    const ids = error.mock.calls.map(([, options]) => (options as { id: string }).id);
    expect(new Set(ids).size).toBe(2);
  });
});
