import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const manager = vi.hoisted(() => ({
  get: vi.fn(),
  set: vi.fn(),
  ensureKeyLoaded: vi.fn(),
}));

vi.mock('@/services/config', () => ({
  getConfigSyncManager: () => manager,
}));

type SecretModule = typeof import('@/store/config/privacyRoutingSecret');

describe('privacyRoutingSecret', () => {
  let secret: SecretModule;

  beforeEach(async () => {
    vi.resetModules();
    manager.get.mockReset().mockReturnValue(null);
    manager.set.mockReset();
    manager.ensureKeyLoaded.mockReset().mockResolvedValue(undefined);
    secret = await import('@/store/config/privacyRoutingSecret');
  });

  it('reads an empty key when none was saved', () => {
    expect(secret.readPrivacyRoutingSecret()).toBe('');
    expect(manager.get).toHaveBeenCalledWith('privacyRoutingSecret');
  });

  it('reads the saved key from its own row', () => {
    manager.get.mockReturnValue({ localApiKey: 'sk-local' });

    expect(secret.readPrivacyRoutingSecret()).toBe('sk-local');
  });

  it('writes the key to its own row, and an empty key clears it', () => {
    secret.writePrivacyRoutingSecret('sk-local');
    secret.writePrivacyRoutingSecret('');

    expect(manager.set).toHaveBeenNthCalledWith(1, 'privacyRoutingSecret', { localApiKey: 'sk-local' });
    expect(manager.set).toHaveBeenNthCalledWith(2, 'privacyRoutingSecret', { localApiKey: '' });
  });

  it('waits for the row to be synced before it reads', async () => {
    let synced = false;
    manager.ensureKeyLoaded.mockImplementation(async () => {
      await Promise.resolve();
      synced = true;
    });
    manager.get.mockImplementation(() => (synced ? { localApiKey: 'sk-after-sync' } : null));

    await expect(secret.loadPrivacyRoutingSecret()).resolves.toBe('sk-after-sync');
  });

  describe('loading the row', () => {
    beforeEach(() => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date('2026-01-01T00:00:00Z'));
    });

    afterEach(() => {
      vi.useRealTimers();
      vi.restoreAllMocks();
    });

    it('does not ask the backend for a row that is already cached', async () => {
      manager.get.mockReturnValue({ localApiKey: 'sk-cached' });

      await expect(secret.loadPrivacyRoutingSecret()).resolves.toBe('sk-cached');
      await secret.loadPrivacyRoutingSecret();

      expect(manager.ensureKeyLoaded).not.toHaveBeenCalled();
    });

    it('treats a row that holds an empty key as cached', async () => {
      manager.get.mockReturnValue({ localApiKey: '' });

      await expect(secret.loadPrivacyRoutingSecret()).resolves.toBe('');

      expect(manager.ensureKeyLoaded).not.toHaveBeenCalled();
    });

    it('asks for a row that does not exist once per window, then again', async () => {
      await secret.loadPrivacyRoutingSecret();
      await secret.loadPrivacyRoutingSecret();
      expect(manager.ensureKeyLoaded).toHaveBeenCalledTimes(1);
      expect(manager.ensureKeyLoaded).toHaveBeenCalledWith('privacyRoutingSecret');

      vi.advanceTimersByTime(10_000);
      await secret.loadPrivacyRoutingSecret();

      expect(manager.ensureKeyLoaded).toHaveBeenCalledTimes(2);
    });

    it('shares one request between calls that arrive together', async () => {
      let finish: () => void = () => undefined;
      manager.ensureKeyLoaded.mockImplementation(
        () =>
          new Promise<void>((resolve) => {
            finish = resolve;
          }),
      );

      const calls = Promise.all([secret.loadPrivacyRoutingSecret(), secret.loadPrivacyRoutingSecret()]);
      finish();
      await calls;

      expect(manager.ensureKeyLoaded).toHaveBeenCalledTimes(1);
    });

    it('does not block the caller when the row cannot be loaded, and picks it up once it can', async () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
      manager.ensureKeyLoaded.mockRejectedValueOnce(new Error('offline'));

      await expect(secret.loadPrivacyRoutingSecret()).resolves.toBe('');
      expect(warn).toHaveBeenCalledTimes(1);

      manager.get.mockReturnValue({ localApiKey: 'sk-recovered' });
      manager.ensureKeyLoaded.mockResolvedValue(undefined);
      await expect(secret.loadPrivacyRoutingSecret()).resolves.toBe('sk-recovered');
    });

    it('asks again after the window when an earlier request got nothing', async () => {
      vi.spyOn(console, 'warn').mockImplementation(() => undefined);
      manager.ensureKeyLoaded.mockRejectedValueOnce(new Error('offline'));
      await secret.loadPrivacyRoutingSecret();

      vi.advanceTimersByTime(10_000);
      manager.ensureKeyLoaded.mockImplementation(async () => {
        manager.get.mockReturnValue({ localApiKey: 'sk-late' });
      });

      await expect(secret.loadPrivacyRoutingSecret()).resolves.toBe('sk-late');
      expect(manager.ensureKeyLoaded).toHaveBeenCalledTimes(2);
    });
  });

  describe('buildPrivacyRoutingRequest', () => {
    it('sends no routing without a local model, and does not load the key', async () => {
      await expect(secret.buildPrivacyRoutingRequest(undefined)).resolves.toBeUndefined();
      await expect(secret.buildPrivacyRoutingRequest({ s3Strategy: 'block' })).resolves.toBeUndefined();

      expect(manager.ensureKeyLoaded).not.toHaveBeenCalled();
    });

    it('adds the saved key to a copy of the routing preferences', async () => {
      manager.get.mockReturnValue({ localApiKey: 'sk-local' });
      const preferences = { localModel: 'llama3:8b', localBaseUrl: 'http://localhost:11434/v1' };

      const request = await secret.buildPrivacyRoutingRequest(preferences);

      expect(request).toEqual({ ...preferences, localApiKey: 'sk-local' });
      expect(preferences).not.toHaveProperty('localApiKey');
    });

    it('leaves the key out when none is saved or it was cleared', async () => {
      const preferences = { localModel: 'llama3:8b' };

      await expect(secret.buildPrivacyRoutingRequest(preferences)).resolves.toEqual(preferences);
      manager.get.mockReturnValue({ localApiKey: '' });
      const cleared = await secret.buildPrivacyRoutingRequest(preferences);
      expect(cleared).toEqual(preferences);
      expect(cleared).not.toHaveProperty('localApiKey');
    });
  });
});
