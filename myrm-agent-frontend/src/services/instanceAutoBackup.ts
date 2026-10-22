/**
 * [INPUT]
 * - @/lib/api: apiRequest (POS: authenticated backend client)
 *
 * [OUTPUT]
 * - AutoBackup / AutoBackupSettings / StoredBackup: wire types of /instance-archive/auto-backup
 * - instanceAutoBackupService: read the schedule, save it, back up now
 *
 * [POS]
 * Frontend client of the scheduled whole-instance backup. Calls are silent: the UI maps the
 * stable error `code` (see `archiveErrorCode` in ./instanceArchive) to localized copy.
 */

import { apiRequest } from '@/lib/api';

const BASE = '/instance-archive/auto-backup';

export type BackupFrequency = 'daily' | 'weekly';

export interface StoredBackup {
  name: string;
  /** When the backup was taken (ISO, UTC). */
  created_at: string;
  size_bytes: number;
}

export interface AutoBackup {
  /** False where scheduled backups are not offered (cloud sandbox, unusual layout). */
  supported: boolean;
  enabled: boolean;
  frequency: BackupFrequency;
  keep: number;
  /** Where backups are written. */
  directory: string;
  default_directory: boolean;
  /** False when the folder cannot be read right now (drive unplugged, share offline): its backups are unknown, not gone. */
  folder_available: boolean;
  running: boolean;
  /** Enabled, but no completed backup for much longer than the chosen frequency. */
  overdue: boolean;
  last_success_at: string | null;
  last_success_size: number | null;
  consecutive_failures: number;
  last_error_code: string | null;
  /** Newest first. */
  backups: StoredBackup[];
}

export interface AutoBackupSettings {
  enabled: boolean;
  frequency: BackupFrequency;
  keep: number;
  /** Null for the default folder. */
  directory: string | null;
}

export const KEEP_MIN = 1;
export const KEEP_MAX = 10;

const silent = { silent: true } as const;

export const instanceAutoBackupService = {
  get: (): Promise<AutoBackup> => apiRequest<AutoBackup>(BASE, { method: 'GET', ...silent }),

  update: (settings: AutoBackupSettings): Promise<AutoBackup> =>
    apiRequest<AutoBackup>(BASE, { method: 'PUT', body: JSON.stringify(settings), ...silent }),

  /** Starts a backup in the background; poll `get` until `running` is false. */
  runNow: (): Promise<AutoBackup> => apiRequest<AutoBackup>(`${BASE}/run`, { method: 'POST', ...silent }),
};
