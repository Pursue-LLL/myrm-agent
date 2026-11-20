/**
 * [INPUT]
 * - `./conflictResolution` RecordSink / adoptServerRecord (POS: the live caches the sync layer hands to its helpers)
 * - `./configFingerprint` valuesEqual (POS: structural equality of config values)
 * - `./types` ConfigAdapter / ConfigKey (POS: backend access and key union)
 *
 * [OUTPUT]
 * reloadKeysFromServer: replaces the cached copies of the given keys with what the server holds now.
 *
 * [POS]
 * The sync layer neither polls nor subscribes to the backend: it reads the configuration at startup (progressively in
 * Sandbox mode) and afterwards reads a key again only when one of its own writes hits a version conflict or a caller
 * asks for a reload. A backend writer that runs while the page is open (the migration wizard edits model slots, MCP
 * servers and global instructions; a plugin import or uninstall edits the MCP servers) leaves the cache behind: the
 * settings pages show the old values, and the next save carries the old merge base into a version conflict that, for a
 * list such as the providers, can only be settled by dropping one side. Callers hand in the live caches through
 * `RecordSink`; nothing here holds state.
 */
import { valuesEqual } from './configFingerprint';
import { adoptServerRecord } from './conflictResolution';
import type { RecordSink } from './conflictResolution';
import type { ConfigAdapter, ConfigKey } from './types';

/**
 * Adopts the server's current record of each key, so the cache, the merge base and the subscribers all move onto it.
 * Two kinds of key stay as they are: one whose cached value differs from its merge base holds an edit the server has
 * not seen (the regular sync settles it), and one written locally while the read was in flight is newer than the
 * answer, which was produced before that write.
 */
export async function reloadKeysFromServer(
  ctx: RecordSink & { adapter: Pick<ConfigAdapter, 'getAll'> },
  keys: readonly ConfigKey[],
): Promise<void> {
  const cachedWhenAsked = new Map(keys.map((key) => [key, ctx.cache.get(key)]));
  for (const [key, serverRecord] of await ctx.adapter.getAll(keys)) {
    const cached = ctx.cache.get(key);
    const base = ctx.baseCache.get(key);
    const hasUnsyncedEdit = cached !== undefined && base !== undefined && !valuesEqual(cached.value, base.value);
    const writtenMeanwhile = cached !== cachedWhenAsked.get(key);
    if (hasUnsyncedEdit || writtenMeanwhile || cached?.meta.version === serverRecord.meta.version) {
      continue;
    }
    adoptServerRecord(ctx, key, serverRecord);
  }
}
