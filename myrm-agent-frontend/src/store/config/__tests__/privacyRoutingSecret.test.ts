import { beforeEach, describe, expect, it, vi } from 'vitest';

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

  it('asks the backend for the row once per page session, even when none exists', async () => {
    await secret.loadPrivacyRoutingSecret();
    await secret.loadPrivacyRoutingSecret();
    await secret.loadPrivacyRoutingSecret();

    expect(manager.ensureKeyLoaded).toHaveBeenCalledTimes(1);
    expect(manager.ensureKeyLoaded).toHaveBeenCalledWith('privacyRoutingSecret');
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
