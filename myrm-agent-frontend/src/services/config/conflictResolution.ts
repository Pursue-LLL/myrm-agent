/**
 * [INPUT]
 * - `./mergeUtils` threeWayMerge (POS: structural three-way merge of config values)
 * - `./types` ConfigAdapter / ConfigChange / ConfigRecord (POS: backend access and record shapes)
 *
 * [OUTPUT]
 * ConfigConflictResolution / ConfigConflictResolver: the context and hook through which the user settles a version conflict.
 * resolveConflicts: reconciles locally cached configs with the server after the backend rejected a write on version.
 * RecordSink / adoptServerRecord: make a record the server holds the cached copy, the merge base and the subscribers' news.
 *
 * [POS]
 * Conflict tiers of the config sync layer (see `_ARCH.md`): a clean three-way merge is applied silently, a conflict on
 * the same device keeps the local value, a conflict across devices asks the resolver. A key that was never loaded has
 * no baseline: what only the server holds is kept, and a clash, even with this device's own write, goes to the
 * resolver. The local cache is the user's latest intent, so a version mismatch alone never discards it. Callers hand
 * in the live caches through `ConflictContext`; nothing here holds state.
 */
import { cloneDeep } from 'lodash-es';
import { threeWayMerge } from './mergeUtils';
import type { ConfigAdapter, ConfigChange, ConfigKey, ConfigRecord, ConfigValueMap } from './types';

/**
 * 配置冲突上下文
 */
export interface ConfigConflictResolution {
  configKey: ConfigKey;
  localVersion: string;
  serverVersion: string;
  deviceId: string;
  localValue?: unknown;
  serverValue?: unknown;
}

/**
 * 冲突解决器
 */
export type ConfigConflictResolver = (conflict: ConfigConflictResolution) => Promise<boolean> | boolean;

/** Where a record adopted from the server lands: the cached copy, the merge base and the subscribers. */
export interface RecordSink {
  cache: Map<ConfigKey, ConfigRecord>;
  baseCache: Map<ConfigKey, ConfigRecord>;
  notify: (key: ConfigKey, value: ConfigValueMap[ConfigKey], meta: ConfigRecord['meta']) => void;
}

export interface ConflictContext extends RecordSink {
  adapter: ConfigAdapter;
  deviceId: string;
  resolver: ConfigConflictResolver | null;
  /** Queue changes whose retry failed so the next sync (and, for allowlisted keys, a reload) picks them up. */
  requeue: (changes: ConfigChange[]) => void;
}

/**
 * 解决冲突：以本地缓存为准，用服务端版本号重新同步。
 * 本地缓存始终是用户最新操作的结果，冲突仅因版本号不匹配，不应丢弃本地数据。
 */
export async function resolveConflicts(ctx: ConflictContext, conflictKeys: ConfigKey[]): Promise<void> {
  const retryChanges: ConfigChange[] = [];

  for (const key of conflictKeys) {
    try {
      const retry = await reconcileKey(ctx, key);
      if (retry) {
        retryChanges.push(retry);
      }
    } catch (error) {
      console.warn(`[ConfigSync] Failed to resolve conflict for '${key}':`, error);
    }
  }

  if (retryChanges.length === 0) {
    return;
  }
  // 用正确的版本号重新同步本地数据
  try {
    const result = await ctx.adapter.sync(retryChanges);
    if (result.success) {
      for (const [key, version] of result.newVersions) {
        const record = ctx.cache.get(key);
        if (record) {
          record.meta.version = version;
          const baseRecord = ctx.baseCache.get(key);
          if (baseRecord) {
            baseRecord.meta.version = version;
          }
        }
      }
    } else {
      // 重试失败，放回队列，保护本地数据不被服务端覆盖
      console.warn('[ConfigSync] Conflict retry failed, saving to offline queue');
      ctx.requeue(retryChanges);
    }
  } catch (error) {
    console.warn('[ConfigSync] Conflict retry error, saving to offline queue:', error);
    ctx.requeue(retryChanges);
  }
}

/** Settles one key; returns the change to re-send with the server's version, or null when nothing is left to send. */
async function reconcileKey(ctx: ConflictContext, key: ConfigKey): Promise<ConfigChange | null> {
  const serverRecord = await ctx.adapter.get(key);
  if (!serverRecord) {
    return null;
  }
  const localRecord = ctx.cache.get(key);
  if (!localRecord) {
    adoptServerRecord(ctx, key, serverRecord);
    return null;
  }

  const baseValue = ctx.baseCache.get(key)?.value as Record<string, unknown> | null | undefined;
  const mergeResult = threeWayMerge(
    baseValue,
    localRecord.value as Record<string, unknown>,
    serverRecord.value as Record<string, unknown>,
  );
  if (!mergeResult.hasConflict) {
    // 自动合并成功，静默处理
    localRecord.value = mergeResult.merged as ConfigValueMap[typeof key];
    const retry = rebaseLocalRecord(ctx, key, localRecord, serverRecord);
    ctx.notify(key, localRecord.value, localRecord.meta);
    return retry;
  }

  // 同浏览器 profile 冲突：静默保留本地，不打扰用户。前提是有基线（本地值由服务端值改来）；
  // 没有基线时本地值从未见过服务端内容，静默保留会抹掉服务端的数据，必须问用户。
  let keepLocal = Boolean(baseValue) && serverRecord.meta.deviceId === ctx.deviceId;
  if (!keepLocal) {
    keepLocal = ctx.resolver
      ? await Promise.resolve(
          ctx.resolver({
            configKey: key,
            localVersion: localRecord.meta.version,
            serverVersion: serverRecord.meta.version,
            deviceId: serverRecord.meta.deviceId,
            localValue: localRecord.value,
            serverValue: serverRecord.value,
          }),
        ).catch((error: unknown) => {
          console.warn(`[ConfigSync] Conflict resolver failed for '${key}':`, error);
          return true;
        })
      : true;
  }

  if (keepLocal !== false) {
    return rebaseLocalRecord(ctx, key, localRecord, serverRecord);
  }
  adoptServerRecord(ctx, key, serverRecord);
  return null;
}

/** Keeps the local value but moves its version onto the server's, so the re-sent change passes the version check. */
function rebaseLocalRecord(
  ctx: ConflictContext,
  key: ConfigKey,
  localRecord: ConfigRecord,
  serverRecord: ConfigRecord,
): ConfigChange {
  localRecord.meta.version = serverRecord.meta.version;
  ctx.baseCache.set(key, cloneDeep(serverRecord));
  return {
    key,
    value: localRecord.value,
    expectedVersion: serverRecord.meta.version,
    timestamp: Date.now(),
  };
}

export function adoptServerRecord(sink: RecordSink, key: ConfigKey, serverRecord: ConfigRecord): void {
  sink.cache.set(key, serverRecord);
  sink.baseCache.set(key, cloneDeep(serverRecord));
  sink.notify(key, serverRecord.value, serverRecord.meta);
}
