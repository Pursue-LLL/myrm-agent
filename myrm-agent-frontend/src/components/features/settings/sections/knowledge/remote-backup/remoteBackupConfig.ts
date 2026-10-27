/**
 * [INPUT]
 * - @/services/config::BackupSyncConfigValue (POS: the stored `backupSync` settings)
 *
 * [OUTPUT]
 * - DEFAULT_CONFIG / withDefaults: the settings a new or older stored value is brought to
 * - SYNC_INTERVAL_CHOICES / snapInterval: the backup frequencies the card offers
 * - keepChoices / clampKeep: how many backups to keep
 * - isConnectionFilled: whether the chosen provider has enough to try a connection
 *
 * [POS]
 * Values the cloud sync card offers and how stored settings are brought into them. The server checks once an hour and
 * honours 60..1440 minutes, so the card offers exactly the frequencies it can keep; an older or hand-edited value is
 * brought to the nearest one instead of silently meaning something else.
 */

import type { BackupSyncConfigValue } from '@/services/config';

export const SYNC_INTERVAL_CHOICES = [
  { minutes: 60, labelKey: 'hourly' },
  { minutes: 360, labelKey: 'every6h' },
  { minutes: 720, labelKey: 'every12h' },
  { minutes: 1440, labelKey: 'daily' },
] as const;

export const DEFAULT_SYNC_INTERVAL = 1440;

export const KEEP_MIN = 1;
export const KEEP_MAX = 100;
export const DEFAULT_KEEP = 10;
const KEEP_CHOICES = [3, 5, 10, 20, 50];

export const DEFAULT_CONFIG: BackupSyncConfigValue = {
  enabled: false,
  provider: 'webdav',
  autoSync: false,
  syncInterval: DEFAULT_SYNC_INTERVAL,
  maxBackups: DEFAULT_KEEP,
  deviceName: '',
  webdav: { host: '', username: '', password: '', path: '/myrm-backups' },
  s3: {
    endpoint: '',
    region: '',
    bucket: '',
    accessKeyId: '',
    secretAccessKey: '',
    prefix: 'myrm-backups/',
    forcePathStyle: true,
  },
};

/** The offered frequency nearest to a stored number of minutes; equally near ones resolve to the longer. */
export function snapInterval(minutes: unknown): number {
  if (typeof minutes !== 'number' || !Number.isFinite(minutes)) {
    return DEFAULT_SYNC_INTERVAL;
  }
  return SYNC_INTERVAL_CHOICES.reduce((nearest, { minutes: choice }) => {
    const distance = Math.abs(choice - minutes);
    const nearestDistance = Math.abs(nearest - minutes);
    return distance < nearestDistance || (distance === nearestDistance && choice > nearest) ? choice : nearest;
  }, DEFAULT_SYNC_INTERVAL);
}

export function clampKeep(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return DEFAULT_KEEP;
  }
  return Math.min(Math.max(Math.round(value), KEEP_MIN), KEEP_MAX);
}

/** The offered counts, plus the stored one when it is not among them, so a saved value never disappears. */
export function keepChoices(current: number): number[] {
  return [...new Set([...KEEP_CHOICES, current])].sort((a, b) => a - b);
}

export function withDefaults(saved: Partial<BackupSyncConfigValue> | undefined): BackupSyncConfigValue {
  return {
    ...DEFAULT_CONFIG,
    ...saved,
    syncInterval: snapInterval(saved?.syncInterval),
    maxBackups: clampKeep(saved?.maxBackups),
    webdav: { ...DEFAULT_CONFIG.webdav, ...saved?.webdav },
    s3: { ...DEFAULT_CONFIG.s3, ...saved?.s3 },
  };
}

export function isConnectionFilled(config: BackupSyncConfigValue): boolean {
  return config.provider === 'webdav' ? config.webdav.host.trim() !== '' : config.s3.endpoint.trim() !== '';
}
