/**
 * [INPUT]
 * - @/lib/api::fetchWithTimeout (POS: unified request entry: local backend gate, API base URL, credentials, logout on 401/403)
 * - @/services/config::BackupSyncConfigValue (POS: the settings a call is made with)
 *
 * [OUTPUT]
 * - checkConnection / listBackups / runBackup / restoreBackup / deleteBackup / fetchAutoStatus: typed calls of `/memory/backup/remote/*`
 * - RemoteBackupFile / AutoSyncStatus / BackupResult / RestoreResult: what they return
 * - errorCodeKey: the localized reason key of a backup that did not succeed
 *
 * [POS]
 * The only place the cloud sync card talks to the server. Every call carries the settings as typed in the form, so what is
 * tried is what is on screen. A listing the server could not read throws instead of reading as an empty storage, and a
 * backup that did not succeed reports its stable error code, never the server's wording. Backups and restores move a
 * whole snapshot and the server retries uploads itself, so the client never gives up on them first.
 */

import { fetchWithTimeout } from '@/lib/api';
import type { BackupSyncConfigValue } from '@/services/config';

const BASE = '/memory/backup/remote';
const NO_TIMEOUT = 0;

export interface RemoteBackupFile {
  file_name: string;
  modified_time: string;
  size_bytes: number;
}

export interface AutoSyncStatus {
  last_success_at: string | null;
  last_attempt_at: string | null;
  last_error_code: string | null;
  consecutive_failures: number;
}

export interface BackupResult {
  success: boolean;
  errorCode: string | null;
}

export interface RestoreResult {
  success: boolean;
  restoredCount: number;
}

export type ErrorCodeKey = 'config' | 'snapshot' | 'upload' | 'busy' | 'internal';

const KNOWN_ERROR_CODES: readonly string[] = ['config', 'snapshot', 'upload', 'busy'];

/** The reason a backup reported; a code this card does not know reads as an internal error. */
export function errorCodeKey(code: string | null | undefined): ErrorCodeKey {
  return code && KNOWN_ERROR_CODES.includes(code) ? (code as ErrorCodeKey) : 'internal';
}

function requestBody(config: BackupSyncConfigValue): Record<string, unknown> {
  const body: Record<string, unknown> = {
    provider: config.provider,
    device_name: config.deviceName,
    max_backups: config.maxBackups,
  };
  if (config.provider === 'webdav') {
    body.webdav = config.webdav;
  } else {
    body.s3 = {
      endpoint: config.s3.endpoint,
      region: config.s3.region,
      bucket: config.s3.bucket,
      access_key_id: config.s3.accessKeyId,
      secret_access_key: config.s3.secretAccessKey,
      prefix: config.s3.prefix,
      force_path_style: config.s3.forcePathStyle,
    };
  }
  return body;
}

// Every route is spelled out in full at its call site: the server's route-caller gate finds callers by path literal.
function post(endpoint: string, body: Record<string, unknown>, timeout?: number): Promise<Response> {
  return fetchWithTimeout(
    endpoint,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
    timeout,
  );
}

export async function checkConnection(config: BackupSyncConfigValue): Promise<boolean> {
  const response = await post(`${BASE}/check-connection`, requestBody(config));
  if (!response.ok) {
    return false;
  }
  const data = (await response.json()) as { connected?: boolean };
  return data.connected === true;
}

/** Throws when the storage could not be read: an unreadable storage is not an empty one. */
export async function listBackups(config: BackupSyncConfigValue): Promise<RemoteBackupFile[]> {
  const response = await post(`${BASE}/list`, requestBody(config));
  if (!response.ok) {
    throw new Error(`Listing the cloud backups failed (${response.status})`);
  }
  const data = (await response.json()) as { files?: RemoteBackupFile[] };
  return data.files ?? [];
}

export async function runBackup(config: BackupSyncConfigValue): Promise<BackupResult> {
  const response = await post(`${BASE}/trigger`, requestBody(config), NO_TIMEOUT);
  if (!response.ok) {
    return { success: false, errorCode: null };
  }
  const data = (await response.json()) as { success?: boolean; error_code?: string | null };
  return { success: data.success === true, errorCode: data.error_code ?? null };
}

export async function restoreBackup(config: BackupSyncConfigValue, fileName: string): Promise<RestoreResult> {
  const response = await post(`${BASE}/restore`, { ...requestBody(config), file_name: fileName }, NO_TIMEOUT);
  if (!response.ok) {
    return { success: false, restoredCount: 0 };
  }
  const data = (await response.json()) as { success?: boolean; restored_count?: number | null };
  return { success: data.success === true, restoredCount: data.restored_count ?? 0 };
}

export async function deleteBackup(config: BackupSyncConfigValue, fileName: string): Promise<boolean> {
  const response = await post(`${BASE}/delete`, { ...requestBody(config), file_name: fileName });
  if (!response.ok) {
    return false;
  }
  const data = (await response.json()) as { success?: boolean };
  return data.success === true;
}

/** How the scheduled backup is doing; null when the server cannot say. */
export async function fetchAutoStatus(): Promise<AutoSyncStatus | null> {
  const response = await fetchWithTimeout(`${BASE}/auto-status`);
  return response.ok ? ((await response.json()) as AutoSyncStatus) : null;
}
