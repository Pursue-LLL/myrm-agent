import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { OauthCredentialRecord } from '../credentialsConstants';
import { resolveOauthCardState } from '../credentialsOAuthUtils';

const NOW_MS = Date.UTC(2026, 9, 14, 12, 0, 0);
const NOW_S = NOW_MS / 1000;
const HOUR_S = 3600;
const DAY_S = 86_400;

function record(overrides: Partial<OauthCredentialRecord>): OauthCredentialRecord {
  return { issuer: 'xai', connected: true, ...overrides };
}

describe('resolveOauthCardState', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW_MS);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows a missing card when there is no credential or it is not connected', () => {
    expect(resolveOauthCardState(undefined)).toEqual({ state: 'missing', daysLeft: 0 });
    expect(resolveOauthCardState(record({ connected: false }))).toEqual({ state: 'missing', daysLeft: 0 });
  });

  describe('credential that renews its own access token', () => {
    it('stays connected right after login, when the access token has hours left', () => {
      const fresh = record({ renewable: true, expires_at: NOW_S + 6 * HOUR_S });

      expect(resolveOauthCardState(fresh)).toEqual({ state: 'connected', daysLeft: 0 });
    });

    it('stays connected after the access token lapsed while the app was idle', () => {
      const idle = record({ renewable: true, expires_at: NOW_S - 7 * HOUR_S });

      expect(resolveOauthCardState(idle)).toEqual({ state: 'connected', daysLeft: 0 });
    });

    it('is expired once the provider rejected its refresh token, even with a valid access token', () => {
      const rejected = record({ renewable: true, needs_reauth: true, expires_at: NOW_S + 6 * HOUR_S });

      expect(resolveOauthCardState(rejected)).toEqual({ state: 'expired', daysLeft: 0 });
    });
  });

  describe('credential that cannot renew itself', () => {
    it('warns with the days left when the token expires within a week', () => {
      expect(resolveOauthCardState(record({ expires_at: NOW_S + 3 * DAY_S + HOUR_S }))).toEqual({
        state: 'expiring',
        daysLeft: 4,
      });
      expect(resolveOauthCardState(record({ expires_at: NOW_S + 2 * HOUR_S }))).toEqual({
        state: 'expiring',
        daysLeft: 1,
      });
    });

    it('is expired after the token expiry', () => {
      expect(resolveOauthCardState(record({ expires_at: NOW_S - 1 }))).toEqual({ state: 'expired', daysLeft: 0 });
    });

    it('is connected when the token lasts beyond a week or never expires', () => {
      expect(resolveOauthCardState(record({ expires_at: NOW_S + 30 * DAY_S }))).toEqual({
        state: 'connected',
        daysLeft: 0,
      });
      expect(resolveOauthCardState(record({}))).toEqual({ state: 'connected', daysLeft: 0 });
    });
  });
});
