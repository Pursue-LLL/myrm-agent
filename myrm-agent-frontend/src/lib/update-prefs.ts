/**
 * [INPUT]
 * - (localStorage)
 *
 * [OUTPUT]
 * - getDeferredVersion, setDeferredVersion, clearDeferredVersion, isDeferred
 * - getQuietHours, setQuietHours, isQuietNow, QuietHours
 *
 * [POS]
 * Update preference helpers for the Stack Update Panel.
 * Deferred versions and quiet hours live in localStorage (per-device, no backend round-trip).
 * All readers are defensive: corrupt or missing values degrade to "no preference".
 */

const DEFERRED_VERSION_KEY = 'myrm-update-deferred-version';
const QUIET_HOURS_KEY = 'myrm-update-quiet-hours';
const AUTO_BACKUP_KEY = 'myrm-update-auto-backup';

export interface QuietHours {
  startHour: number;
  endHour: number;
}

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Quota exceeded or private mode — preferences simply don't persist.
  }
}

export function getDeferredVersion(): string | null {
  return readStorage(DEFERRED_VERSION_KEY);
}

export function setDeferredVersion(version: string): void {
  writeStorage(DEFERRED_VERSION_KEY, version);
}

export function clearDeferredVersion(): void {
  try {
    localStorage.removeItem(DEFERRED_VERSION_KEY);
  } catch {
    // Best effort only.
  }
}

export function isDeferred(version: string | null | undefined): boolean {
  if (!version) {
    return false;
  }
  return getDeferredVersion() === version;
}

export function getQuietHours(): QuietHours | null {
  const raw = readStorage(QUIET_HOURS_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed === 'object' &&
      parsed !== null &&
      typeof (parsed as { startHour?: unknown }).startHour === 'number' &&
      typeof (parsed as { endHour?: unknown }).endHour === 'number'
    ) {
      const { startHour, endHour } = parsed as { startHour: number; endHour: number };
      if (
        Number.isInteger(startHour) &&
        Number.isInteger(endHour) &&
        startHour >= 0 &&
        startHour <= 23 &&
        endHour >= 0 &&
        endHour <= 23 &&
        startHour !== endHour
      ) {
        return { startHour, endHour };
      }
    }
    return null;
  } catch {
    return null;
  }
}

export function setQuietHours(hours: QuietHours | null): void {
  if (hours === null) {
    try {
      localStorage.removeItem(QUIET_HOURS_KEY);
    } catch {
      // Best effort only.
    }
    return;
  }
  writeStorage(QUIET_HOURS_KEY, JSON.stringify(hours));
}

/** Auto pre-update snapshots default ON; explicit off persists. */
export function getAutoBackup(): boolean {
  const raw = readStorage(AUTO_BACKUP_KEY);
  if (raw === null) {
    return true;
  }
  return raw !== 'false';
}

export function setAutoBackup(enabled: boolean): void {
  writeStorage(AUTO_BACKUP_KEY, enabled ? 'true' : 'false');
}

/** True when `now` falls inside the quiet window (wraps midnight). */
export function isQuietNow(hours: QuietHours | null, now: Date = new Date()): boolean {
  if (!hours) {
    return false;
  }
  const current = now.getHours();
  if (hours.startHour < hours.endHour) {
    return current >= hours.startHour && current < hours.endHour;
  }
  return current >= hours.startHour || current < hours.endHour;
}
