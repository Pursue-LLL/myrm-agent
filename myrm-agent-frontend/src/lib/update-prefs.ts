/**
 * Update preference helpers for the Stack Update Panel.
 *
 * Deferred versions, quiet hours, and post-update receipts live in
 * localStorage (per-device, no backend round-trip). All readers are
 * defensive: corrupt or missing values degrade to "no preference".
 */

const DEFERRED_VERSION_KEY = 'myrm-update-deferred-version';
const QUIET_HOURS_KEY = 'myrm-update-quiet-hours';
const JUST_UPDATED_KEY = 'myrm-just-updated';

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

export interface UpdateReceipt {
  fromVersion: string;
  toVersion: string;
  at: string;
}

export function saveUpdateReceipt(receipt: UpdateReceipt): void {
  writeStorage(JUST_UPDATED_KEY, JSON.stringify(receipt));
}

/** Read-and-clear: the receipt shows once after restart, then disappears. */
export function takeUpdateReceipt(): UpdateReceipt | null {
  const raw = readStorage(JUST_UPDATED_KEY);
  if (!raw) {
    return null;
  }
  try {
    localStorage.removeItem(JUST_UPDATED_KEY);
  } catch {
    // Best effort only.
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed === 'object' &&
      parsed !== null &&
      typeof (parsed as { toVersion?: unknown }).toVersion === 'string'
    ) {
      return parsed as UpdateReceipt;
    }
    return null;
  } catch {
    return null;
  }
}
