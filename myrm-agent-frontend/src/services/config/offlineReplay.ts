/**
 * [INPUT]
 * - `./configFingerprint` valuesEqual (POS: deep equality for config values)
 * - `./conflictResolution` ConfigConflictResolver (POS: user-facing decision hook)
 * - `./types` ConfigChange / ConfigRecord (POS: queued write and server-confirmed record)
 *
 * [OUTPUT]
 * partitionOfflineChanges: which queued changes are still safe to replay against the current server state.
 * mergeLatestChanges: one change per key (the latest value) ready to send to the backend.
 *
 * [POS]
 * Replay decisions of the config sync layer, free of manager state: callers hand in the server records and the
 * resolver they hold. A queued change records the server version it was based on; when the server has moved on, the
 * snapshot is stale and replaying it would overwrite newer configuration.
 */
import { valuesEqual } from './configFingerprint';
import type { ConfigConflictResolver } from './conflictResolution';
import type { ConfigChange, ConfigKey, ConfigRecord } from './types';
import { createInitialVersion } from './types';

/**
 * Latest change per key. `expectedVersion` comes from `baseCache` (the latest confirmed server version) so consecutive
 * local edits never conflict with themselves; offline replay keeps the recorded base version instead.
 */
export function mergeLatestChanges(
  changes: ConfigChange[],
  baseCache: ReadonlyMap<ConfigKey, ConfigRecord>,
  preserveExpectedVersion = false,
): ConfigChange[] {
  const latestByKey = new Map<ConfigKey, ConfigChange>();
  for (const change of changes) {
    latestByKey.set(change.key, change);
  }
  return Array.from(latestByKey.entries()).map(([key, latest]) => {
    if (preserveExpectedVersion) {
      return { ...latest };
    }
    return { ...latest, expectedVersion: baseCache.get(key)?.meta.version ?? latest.expectedVersion };
  });
}

/**
 * Keeps the changes that may still be replayed. Stale ones (the server moved on) are dropped so the server value wins;
 * when a conflict resolver is registered the user decides instead.
 */
export async function partitionOfflineChanges(
  changes: ConfigChange[],
  serverRecords: ReadonlyMap<ConfigKey, ConfigRecord>,
  resolver: ConfigConflictResolver | null,
): Promise<ConfigChange[]> {
  const replayable: ConfigChange[] = [];
  const stale: ConfigChange[] = [];

  for (const change of changes) {
    const serverRecord = serverRecords.get(change.key);
    const serverVersion = serverRecord?.meta.version;
    const baseVersion = change.expectedVersion;

    if (baseVersion !== undefined && serverVersion !== undefined && baseVersion === serverVersion) {
      // The server has not moved since the local edit: the change is still valid.
      replayable.push(change);
      continue;
    }

    if (baseVersion === undefined && serverRecord && valuesEqual(serverRecord.value, change.value)) {
      // The server already holds this value; replaying it would change nothing.
      continue;
    }

    stale.push(change);
  }

  if (stale.length > 0) {
    if (await shouldKeepLocalForStaleChanges(stale, serverRecords, resolver)) {
      replayable.push(...stale);
    } else {
      console.warn(
        '[ConfigSync] Dropped stale offline changes (server moved on):',
        stale.map((change) => change.key).join(', '),
      );
    }
  }

  return replayable;
}

/**
 * Whether stale changes should still overwrite the server: the registered resolver decides. Without one the server
 * value wins — a server configuration must not be replaced by a snapshot whose origin cannot be verified.
 */
async function shouldKeepLocalForStaleChanges(
  changes: ConfigChange[],
  serverRecords: ReadonlyMap<ConfigKey, ConfigRecord>,
  resolver: ConfigConflictResolver | null,
): Promise<boolean> {
  if (!resolver) {
    return false;
  }
  for (const change of changes) {
    const serverRecord = serverRecords.get(change.key);
    const keepLocal = await Promise.resolve(
      resolver({
        configKey: change.key,
        localVersion: change.expectedVersion ?? createInitialVersion(),
        serverVersion: serverRecord?.meta.version ?? createInitialVersion(),
        deviceId: serverRecord?.meta.deviceId ?? 'unknown',
        localValue: change.value,
        serverValue: serverRecord?.value,
      }),
    ).catch((error: unknown) => {
      console.warn('[ConfigSync] Conflict resolver failed for stale offline change:', error);
      return false;
    });
    if (keepLocal) {
      return true;
    }
  }
  return false;
}
