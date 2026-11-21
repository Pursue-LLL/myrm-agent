/**
 * [INPUT]
 * - `./configFingerprint` valuesEqual (POS: deep equality for config values)
 * - `./conflictResolution` ConfigConflictResolver (POS: user-facing decision hook)
 * - `./types` ConfigChange / ConfigKey / ConfigRecord (POS: queued write and server-confirmed record)
 *
 * [OUTPUT]
 * decideReplay: what becomes of each change a previous session left behind: sent, settled without a send, or left for later.
 * mergeLatestChanges: one change per key (the latest value) ready to send to the backend.
 *
 * [POS]
 * Replay decisions of the config sync layer, free of manager state: callers hand in the server records, the keys the
 * server could not be asked about, and the resolver they hold. A queued change records the server version it was
 * based on; when the server has moved on, the snapshot is stale and sending it would overwrite newer configuration, so
 * the user decides, one change at a time, and without a resolver the server value wins. Nothing is made up: a key the
 * server has no row for has nothing to clash with, and a key the server could not be asked about stays as it is.
 */
import { valuesEqual } from './configFingerprint';
import type { ConfigConflictResolver } from './conflictResolution';
import type { ConfigChange, ConfigKey, ConfigRecord } from './types';

/**
 * Latest change per key, on the version the server last confirmed: `expectedVersion` comes from `baseCache` so
 * consecutive local edits never conflict with themselves and a replayed change that was kept goes out on the version
 * the user was shown. A key the server has no record of keeps the version the change recorded.
 */
export function mergeLatestChanges(
  changes: ConfigChange[],
  baseCache: ReadonlyMap<ConfigKey, ConfigRecord>,
): ConfigChange[] {
  const latestByKey = new Map<ConfigKey, ConfigChange>();
  for (const change of changes) {
    latestByKey.set(change.key, change);
  }
  return Array.from(latestByKey.entries()).map(([key, latest]) => ({
    ...latest,
    expectedVersion: baseCache.get(key)?.meta.version ?? latest.expectedVersion,
  }));
}

export interface ReplayDecision {
  /** Still has to reach the server. */
  send: ConfigChange[];
  /** Needs no send: the server already holds the value, or the server's value was chosen. */
  settled: ConfigChange[];
  /** The server could not be asked about the key: nothing is known, so the change waits. */
  undecided: ConfigChange[];
}

/** Sorts `changes` against what the server holds. `unread` are the keys the server could not be asked about. */
export async function decideReplay(
  changes: ConfigChange[],
  serverRecords: ReadonlyMap<ConfigKey, ConfigRecord>,
  unread: ReadonlySet<ConfigKey>,
  resolver: ConfigConflictResolver | null,
): Promise<ReplayDecision> {
  const decision: ReplayDecision = { send: [], settled: [], undecided: [] };
  for (const change of changes) {
    const server = serverRecords.get(change.key);
    if (unread.has(change.key)) {
      decision.undecided.push(change);
    } else if (!server) {
      decision.send.push(change);
    } else if (valuesEqual(server.value, change.value)) {
      decision.settled.push(change);
    } else if (change.expectedVersion === server.meta.version || (await keepsLocal(change, server, resolver))) {
      decision.send.push(change);
    } else {
      console.warn('[ConfigSync] Dropped a stale offline change (server moved on):', change.key);
      decision.settled.push(change);
    }
  }
  return decision;
}

/**
 * Whether a stale change should still overwrite the server: the registered resolver decides. Without one the server
 * value wins — a server configuration must not be replaced by a snapshot whose origin cannot be verified.
 */
async function keepsLocal(
  change: ConfigChange,
  server: ConfigRecord,
  resolver: ConfigConflictResolver | null,
): Promise<boolean> {
  if (!resolver) {
    return false;
  }
  try {
    return await resolver({
      configKey: change.key,
      localVersion: change.expectedVersion,
      serverVersion: server.meta.version,
      deviceId: server.meta.deviceId,
      localValue: change.value,
      serverValue: server.value,
    });
  } catch (error) {
    console.warn('[ConfigSync] Conflict resolver failed for stale offline change:', error);
    return false;
  }
}
