import { describe, expect, it, afterEach } from 'vitest';
import {
  addRemoteProfile,
  ensureCloudProfile,
  getActiveRemoteProfile,
  listRemoteProfiles,
  removeRemoteProfile,
  resolveProfileApiBase,
  setActiveRemoteProfileId,
} from '@/lib/remote-profiles';

function makeWindow(entries: Record<string, string> = {}) {
  const store = new Map(Object.entries(entries));
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      localStorage: {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => {
          store.set(k, v);
        },
        removeItem: (k: string) => {
          store.delete(k);
        },
      },
    },
  });
  return store;
}

describe('remote profiles roster', () => {
  const originalWindow = globalThis.window;

  afterEach(() => {
    Object.defineProperty(globalThis, 'window', { configurable: true, value: originalWindow });
  });

  it('migrates legacy single-slot config once and deletes legacy key', () => {
    const store = makeWindow({
      'myrm-remote-gateway': JSON.stringify({ enabled: true, url: 'https://nuc.example.com/' }),
    });
    const profiles = listRemoteProfiles();
    expect(profiles).toHaveLength(1);
    expect(profiles[0].url).toBe('https://nuc.example.com');
    expect(getActiveRemoteProfile()?.url).toBe('https://nuc.example.com');
    expect(store.has('myrm-remote-gateway')).toBe(false);
  });

  it('rejects duplicate names and urls', () => {
    makeWindow();
    const first = addRemoteProfile('Homelab', 'https://homelab.example.com');
    expect(first).not.toBeNull();
    expect(addRemoteProfile('homelab', 'https://other.example.com')).toBeNull();
    expect(addRemoteProfile('Other', 'https://homelab.example.com')).toBeNull();
  });

  it('creates cloud profiles resolving to the CP proxy base', () => {
    makeWindow();
    const created = addRemoteProfile('Cloud sandbox', 'https://cp.example.com/proxy/me', {
      kind: 'cloud',
      cpBaseUrl: 'https://cp.example.com',
    });
    expect(created?.kind).toBe('cloud');
    expect(created && resolveProfileApiBase(created)).toBe('https://cp.example.com/proxy/me');
    expect(addRemoteProfile('Cloud 2', 'https://other.example.com/proxy/me', { kind: 'cloud' })).toBeNull();
  });

  it('clears active selection on remove', () => {
    makeWindow();
    const created = addRemoteProfile('Homelab', 'https://homelab.example.com');
    expect(getActiveRemoteProfile()?.id).toBe(created?.id);
    removeRemoteProfile(created?.id ?? '');
    expect(getActiveRemoteProfile()).toBeNull();
    expect(setActiveRemoteProfileId('missing')).toBe(false);
  });

  describe('ensureCloudProfile', () => {
    const CP = 'https://cp.example.com';

    it('creates an active cloud profile pointing at the CP proxy', () => {
      makeWindow();

      const profile = ensureCloudProfile('Cloud sandbox', `${CP}/`);

      expect(profile).toMatchObject({ name: 'Cloud sandbox', url: `${CP}/proxy/me`, kind: 'cloud', cpBaseUrl: CP });
      expect(getActiveRemoteProfile()?.id).toBe(profile?.id);
    });

    it('re-activates the existing cloud profile instead of duplicating it', () => {
      makeWindow();
      const first = ensureCloudProfile('Cloud sandbox', CP);
      addRemoteProfile('Home NUC', 'https://nuc.example.com');

      const again = ensureCloudProfile('Cloud sandbox', CP);

      expect(again?.id).toBe(first?.id);
      expect(listRemoteProfiles()).toHaveLength(2);
      expect(getActiveRemoteProfile()?.id).toBe(first?.id);
    });

    it('replaces a non-cloud profile that squats the proxy url', () => {
      makeWindow();
      addRemoteProfile('Manual', `${CP}/proxy/me`);

      const profile = ensureCloudProfile('Cloud sandbox', CP);

      expect(profile?.kind).toBe('cloud');
      expect(listRemoteProfiles().map((p) => p.name)).toEqual(['Cloud sandbox']);
    });

    it('numbers the name when the default one is already taken', () => {
      makeWindow();
      addRemoteProfile('Cloud sandbox', 'https://nuc.example.com');

      const profile = ensureCloudProfile('cloud sandbox', CP);

      expect(profile?.name).toBe('cloud sandbox 2');
      expect(getActiveRemoteProfile()?.id).toBe(profile?.id);
    });

    it('returns null for an invalid control plane address', () => {
      makeWindow();

      expect(ensureCloudProfile('Cloud sandbox', 'not a url')).toBeNull();
      expect(listRemoteProfiles()).toHaveLength(0);
    });
  });
});
