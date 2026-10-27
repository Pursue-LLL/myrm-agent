'use client';

/**
 * [INPUT]
 * - ./remoteBackupApi (POS: typed calls of the cloud backup endpoints)
 * - ./remoteBackupConfig (POS: defaults and the offered values of the settings)
 * - @/services/config::getConfigSyncManager (POS: where the `backupSync` settings are saved and synced across devices)
 *
 * [OUTPUT]
 * - useRemoteBackup: the settings being edited, the cloud backups listed, how the scheduled backup is doing, and the actions on them
 *
 * [POS]
 * State machine of the cloud sync card. The listing carries its own state, so a storage that could not be read shows as such
 * and never as an empty one; the answer of an older request never overwrites a newer one. Every failure is shown as
 * localized copy, never as the server's wording.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { getConfigSyncManager, type BackupSyncConfigValue } from '@/services/config';
import {
  checkConnection,
  deleteBackup,
  errorCodeKey,
  fetchAutoStatus,
  listBackups,
  restoreBackup,
  runBackup,
  type AutoSyncStatus,
  type RemoteBackupFile,
} from './remoteBackupApi';
import { DEFAULT_CONFIG, isConnectionFilled, withDefaults } from './remoteBackupConfig';

export type ListState = 'idle' | 'loading' | 'ready' | 'error';
export type ConnectionState = 'idle' | 'success' | 'failed';

export function useRemoteBackup() {
  const t = useTranslations('settings.remoteBackup');
  const [config, setConfig] = useState<BackupSyncConfigValue>(DEFAULT_CONFIG);
  const [files, setFiles] = useState<RemoteBackupFile[]>([]);
  const [listState, setListState] = useState<ListState>('idle');
  const [status, setStatus] = useState<AutoSyncStatus | null>(null);
  const [connection, setConnection] = useState<ConnectionState>('idle');
  const [testing, setTesting] = useState(false);
  const [backingUp, setBackingUp] = useState(false);
  const latestListing = useRef(0);

  const refreshFiles = useCallback(async (target: BackupSyncConfigValue) => {
    const listing = ++latestListing.current;
    setListState('loading');
    try {
      const listed = await listBackups(target);
      if (listing === latestListing.current) {
        setFiles(listed);
        setListState('ready');
      }
    } catch {
      if (listing === latestListing.current) {
        setFiles([]);
        setListState('error');
      }
    }
  }, []);

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await fetchAutoStatus());
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    const saved = getConfigSyncManager().get('backupSync');
    if (!saved) {
      return;
    }
    const loaded = withDefaults(saved);
    setConfig(loaded);
    if (loaded.enabled) {
      void refreshStatus();
      if (isConnectionFilled(loaded)) {
        void refreshFiles(loaded);
      }
    }
  }, [refreshFiles, refreshStatus]);

  const edit = useCallback((update: (previous: BackupSyncConfigValue) => BackupSyncConfigValue) => {
    setConfig(update);
    setConnection('idle');
  }, []);

  const save = useCallback(() => {
    try {
      getConfigSyncManager().set('backupSync', config);
      toast.success(t('saveSuccess'));
    } catch {
      toast.error(t('saveFailed'));
    }
  }, [config, t]);

  const testConnection = useCallback(async () => {
    setTesting(true);
    setConnection('idle');
    try {
      const connected = await checkConnection(config);
      setConnection(connected ? 'success' : 'failed');
      if (connected) {
        toast.success(t('connectionSuccess'));
        void refreshFiles(config);
      } else {
        toast.error(t('connectionFailed'));
      }
    } catch {
      setConnection('failed');
      toast.error(t('connectionFailed'));
    } finally {
      setTesting(false);
    }
  }, [config, refreshFiles, t]);

  const backupNow = useCallback(async () => {
    setBackingUp(true);
    try {
      const result = await runBackup(config);
      if (result.success) {
        toast.success(t('backupSuccess'));
      } else {
        toast.error(result.errorCode ? t(`errorCodes.${errorCodeKey(result.errorCode)}`) : t('backupError'));
      }
      void refreshFiles(config);
      void refreshStatus();
    } catch {
      toast.error(t('backupError'));
    } finally {
      setBackingUp(false);
    }
  }, [config, refreshFiles, refreshStatus, t]);

  const restore = useCallback(
    async (fileName: string) => {
      try {
        const result = await restoreBackup(config, fileName);
        if (result.success) {
          toast.success(t('restoreSuccess', { count: result.restoredCount }));
        } else {
          toast.error(t('restoreError'));
        }
      } catch {
        toast.error(t('restoreError'));
      }
    },
    [config, t],
  );

  const remove = useCallback(
    async (fileName: string) => {
      try {
        if (await deleteBackup(config, fileName)) {
          toast.success(t('deleteSuccess'));
          void refreshFiles(config);
        } else {
          toast.error(t('deleteFailed'));
        }
      } catch {
        toast.error(t('deleteFailed'));
      }
    },
    [config, refreshFiles, t],
  );

  const reload = useCallback(() => {
    void refreshFiles(config);
  }, [config, refreshFiles]);

  return {
    config,
    files,
    listState,
    status,
    connection,
    testing,
    backingUp,
    edit,
    save,
    testConnection,
    backupNow,
    restore,
    remove,
    reload,
  };
}
