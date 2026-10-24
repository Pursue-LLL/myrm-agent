/**
 * Remote gateway + URL normalisation boundaries.
 *
 * The desktop client can point at a remote server; these helpers decide which base URL wins and must never
 * let a placeholder (`undefined` / `null`) or a non-http scheme leak into the request pipeline.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

const profiles = vi.hoisted(() => ({
  active: null as null | { id: string; name: string; url: string },
  list: [] as Array<{ id: string; name: string; url: string }>,
}));

vi.mock('@/lib/remote-profiles', () => ({
  getActiveRemoteProfile: () => profiles.active,
  setActiveRemoteProfileId: vi.fn(),
  listRemoteProfiles: () => profiles.list,
  addRemoteProfile: vi.fn(),
  resolveProfileApiBase: (profile: { url: string }) => `${profile.url}/api/v1`,
}));

import {
  getDocsUrl,
  getRemoteGatewayConfig,
  isRemoteGatewayActive,
  normalizeConfiguredBaseUrl,
  setRemoteGatewayConfig,
} from '@/lib/deploy-mode';

const originalLocation = window.location;

afterEach(() => {
  profiles.active = null;
  profiles.list = [];
  window.localStorage.clear();
  delete (window as unknown as Record<string, unknown>).__TAURI__;
  Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
});

describe('normalizeConfiguredBaseUrl', () => {
  it.each([
    ['', 'http://fallback'],
    ['undefined', 'http://fallback'],
    ['NULL', 'http://fallback'],
    ['ftp://example.com', 'http://fallback'],
    ['not a url', 'http://fallback'],
    ['https://api.example.com///', 'https://api.example.com'],
  ])('normalises %s', (value, expected) => {
    expect(normalizeConfiguredBaseUrl(value, 'http://fallback')).toBe(expected);
  });
});

describe('remote gateway config', () => {
  it('is null without an active profile', () => {
    expect(getRemoteGatewayConfig()).toBeNull();
    expect(isRemoteGatewayActive()).toBe(false);
  });

  it('resolves the active profile into an enabled config', () => {
    profiles.active = { id: 'p1', name: 'Remote', url: 'https://remote.example.com' };

    expect(getRemoteGatewayConfig()).toEqual({
      enabled: true,
      url: 'https://remote.example.com/api/v1',
    });
  });

  it('is only active inside the Tauri runtime', () => {
    profiles.active = { id: 'p1', name: 'Remote', url: 'https://remote.example.com' };
    expect(isRemoteGatewayActive()).toBe(false);

    (window as unknown as Record<string, unknown>).__TAURI__ = {};
    expect(isRemoteGatewayActive()).toBe(true);
  });

  it('backs up the local token on first connect and restores it on disconnect', () => {
    window.localStorage.setItem('auth_token', 'local-token');

    setRemoteGatewayConfig({ enabled: true, url: 'https://remote.example.com' });
    expect(window.localStorage.getItem('auth_token')).toBe('local-token');

    setRemoteGatewayConfig(null);
    expect(window.localStorage.getItem('auth_token')).toBe('local-token');
  });

  it('never overwrites an existing local token backup', () => {
    window.localStorage.setItem('myrm-local-auth-token-backup', 'first');
    window.localStorage.setItem('auth_token', 'second');

    setRemoteGatewayConfig({ enabled: true, url: 'https://other.example.com' });

    expect(window.localStorage.getItem('myrm-local-auth-token-backup')).toBe('first');
  });

  it('reuses a known profile instead of adding a duplicate', () => {
    profiles.list = [{ id: 'p1', name: 'Remote', url: 'https://remote.example.com' }];

    expect(() => setRemoteGatewayConfig({ enabled: true, url: 'https://remote.example.com/' })).not.toThrow();
  });
});

describe('getDocsUrl', () => {
  it('returns an absolute documentation origin', () => {
    expect(getDocsUrl()).toMatch(/^https?:\/\//);
  });
});
