/**
 * What reloading keys from the server does to the cached copies: the server's value replaces the cache and the merge
 * base and reaches the subscribers, an edit the server has not seen survives, and nothing is announced twice.
 */

import { cloneDeep } from 'lodash-es';
import { describe, expect, it, vi } from 'vitest';
import { reloadKeysFromServer } from '../serverReload';
import type { ConfigAdapter, ConfigKey, ConfigRecord } from '../types';

const record = (key: ConfigKey, value: unknown, version: string): ConfigRecord => ({
  key,
  value: value as never,
  meta: { version, updatedAt: '2026-01-01T00:00:00.000Z', deviceId: 'dev' },
});

/** A cache that holds `cached` (as the copy and as the merge base) and a server that holds `onServer`. */
function reloadContext(cached: ConfigRecord[], onServer: ConfigRecord[]) {
  const getAll = vi.fn().mockResolvedValue(new Map(onServer.map((entry) => [entry.key, entry])));
  const notify = vi.fn();
  const cache = new Map(cached.map((entry) => [entry.key, cloneDeep(entry)]));
  const baseCache = new Map(cached.map((entry) => [entry.key, cloneDeep(entry)]));
  return { ctx: { adapter: { getAll } as unknown as ConfigAdapter, cache, baseCache, notify }, getAll, notify };
}

describe('reloadKeysFromServer', () => {
  it('replaces the cached copy and the merge base with the server value and announces it once', async () => {
    const onServer = record('providers', { providers: [{ id: 'openai', apiKeys: ['imported'] }] }, '1000_5');
    const { ctx, notify } = reloadContext([record('providers', { providers: [] }, '1000_0')], [onServer]);

    await reloadKeysFromServer(ctx, ['providers']);

    expect(ctx.cache.get('providers')).toEqual(onServer);
    expect(ctx.baseCache.get('providers')).toEqual(onServer);
    expect(ctx.baseCache.get('providers')).not.toBe(ctx.cache.get('providers'));
    expect(notify).toHaveBeenCalledExactlyOnceWith('providers', onServer.value, onServer.meta);
  });

  it('asks the server for exactly the keys it was given', async () => {
    const { ctx, getAll } = reloadContext([], []);

    await reloadKeysFromServer(ctx, ['providers', 'mcpServers']);

    expect(getAll).toHaveBeenCalledExactlyOnceWith(['providers', 'mcpServers']);
  });

  it('leaves a key alone while it carries an edit the server has not seen', async () => {
    const synced = record('mcpServers', { mcpConfigs: [] }, '1000_0');
    const { ctx, notify } = reloadContext([synced], [record('mcpServers', { mcpConfigs: [{ name: 'db' }] }, '1000_5')]);
    const edited = record('mcpServers', { mcpConfigs: [{ name: 'mine' }] }, '1000_1');
    ctx.cache.set('mcpServers', edited);

    await reloadKeysFromServer(ctx, ['mcpServers']);

    expect(ctx.cache.get('mcpServers')).toBe(edited);
    expect(ctx.baseCache.get('mcpServers')).toEqual(synced);
    expect(notify).not.toHaveBeenCalled();
  });

  it('leaves a key alone when a local write was acknowledged while the read was in flight', async () => {
    const answeredEarlier = record('personalSettings', { systemInstructions: 'Answer in French.' }, '1000_5');
    const { ctx, getAll, notify } = reloadContext(
      [record('personalSettings', { systemInstructions: '' }, '1000_0')],
      [answeredEarlier],
    );
    const acknowledged = record('personalSettings', { systemInstructions: 'Answer in German.' }, '1000_9');
    getAll.mockImplementation(async () => {
      ctx.cache.set('personalSettings', acknowledged);
      ctx.baseCache.set('personalSettings', cloneDeep(acknowledged));
      return new Map([['personalSettings', answeredEarlier]]);
    });

    await reloadKeysFromServer(ctx, ['personalSettings']);

    expect(ctx.cache.get('personalSettings')).toBe(acknowledged);
    expect(ctx.baseCache.get('personalSettings')).toEqual(acknowledged);
    expect(notify).not.toHaveBeenCalled();
  });

  it('does not announce a key the cache already holds at the server version', async () => {
    const current = record('personalSettings', { systemInstructions: 'Answer in French.' }, '1000_5');
    const { ctx, notify } = reloadContext([current], [cloneDeep(current)]);

    await reloadKeysFromServer(ctx, ['personalSettings']);

    expect(notify).not.toHaveBeenCalled();
  });

  it('adopts a key the cache does not hold yet', async () => {
    const onServer = record('mcpServers', { mcpConfigs: [{ name: 'db' }] }, '1000_5');
    const { ctx, notify } = reloadContext([], [onServer]);

    await reloadKeysFromServer(ctx, ['mcpServers']);

    expect(ctx.cache.get('mcpServers')).toEqual(onServer);
    expect(ctx.baseCache.get('mcpServers')).toEqual(onServer);
    expect(notify).toHaveBeenCalledExactlyOnceWith('mcpServers', onServer.value, onServer.meta);
  });

  it('keeps a key the server does not hold', async () => {
    const cached = record('mcpServers', { mcpConfigs: [] }, '1000_0');
    const { ctx, notify } = reloadContext([cached], []);

    await reloadKeysFromServer(ctx, ['mcpServers']);

    expect(ctx.cache.get('mcpServers')).toEqual(cached);
    expect(notify).not.toHaveBeenCalled();
  });

  it('passes a failed read on and leaves the caches as they were', async () => {
    const cached = record('providers', { providers: [] }, '1000_0');
    const { ctx, getAll, notify } = reloadContext([cached], []);
    getAll.mockRejectedValue(new Error('backend unreachable'));

    await expect(reloadKeysFromServer(ctx, ['providers'])).rejects.toThrow('backend unreachable');

    expect(ctx.cache.get('providers')).toEqual(cached);
    expect(notify).not.toHaveBeenCalled();
  });
});
