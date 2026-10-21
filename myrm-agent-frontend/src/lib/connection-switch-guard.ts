/**
 * [INPUT]
 * - (none: localStorage only, zero module imports)
 *
 * [OUTPUT]
 * - Last-good connection memory + pending-switch verification for safe switches.
 *
 * [POS]
 * Guards ServerConnectionCard profile switches: health-gate before switching,
 * last-known-good rollback when the new target proves unreachable after reload.
 * Snapshots carry the roster profile id (raw profile urls and resolved API
 * bases differ for cloud profiles, so rollback must restore by id and never
 * write new profiles). localStorage only; corrupt values degrade to "no memory".
 */

export interface GatewayConfigSnapshot {
  activeId: string | null;
  url: string | null;
}

const LAST_GOOD_KEY = 'myrm-connection-last-good';
const PENDING_SWITCH_KEY = 'myrm-connection-pending-switch';

/** Crash leftovers older than this are discarded instead of verified. */
export const PENDING_SWITCH_TTL_MS = 10 * 60 * 1000;

export interface PendingSwitch {
  url: string | null;
  at: number;
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
    // Private mode or quota — guards simply don't persist.
  }
}

function removeStorage(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    // Best effort only.
  }
}

export function getLastGood(): GatewayConfigSnapshot | null {
  const raw = readStorage(LAST_GOOD_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) {
      return null;
    }
    const record = parsed as { activeId?: unknown; url?: unknown };
    if (record.activeId !== null && typeof record.activeId !== 'string') {
      return null;
    }
    if (record.url !== null && typeof record.url !== 'string') {
      return null;
    }
    return { activeId: record.activeId, url: record.url };
  } catch {
    return null;
  }
}

export function setLastGood(snapshot: GatewayConfigSnapshot): void {
  writeStorage(LAST_GOOD_KEY, JSON.stringify(snapshot));
}

export function getPendingSwitch(): PendingSwitch | null {
  const raw = readStorage(PENDING_SWITCH_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) {
      return null;
    }
    const record = parsed as { url?: unknown; at?: unknown };
    if (record.url !== null && typeof record.url !== 'string') {
      return null;
    }
    if (typeof record.at !== 'number') {
      return null;
    }
    return { url: record.url, at: record.at };
  } catch {
    return null;
  }
}

export function setPendingSwitch(pending: PendingSwitch): void {
  writeStorage(PENDING_SWITCH_KEY, JSON.stringify(pending));
}

export function clearPendingSwitch(): void {
  removeStorage(PENDING_SWITCH_KEY);
}

export function isPendingFresh(pending: PendingSwitch, now: number = Date.now()): boolean {
  return now - pending.at <= PENDING_SWITCH_TTL_MS;
}
