import { describe, expect, it, afterEach } from 'vitest';
import {
  addRemoteProfile,
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
});
