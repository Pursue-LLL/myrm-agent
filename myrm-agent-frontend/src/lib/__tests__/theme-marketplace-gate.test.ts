import { describe, expect, it } from 'vitest';
import { hasCpMarketplaceJwt } from '@/lib/theme-marketplace-gate';
import { isCpAuthTokenValid, parseCpAuthTokenUserId } from '@/lib/auth-cp-token';

function buildCpTestToken(expirySeconds: number): string {
  const inner = `user_test:${expirySeconds}.fakesignature`;
  return btoa(inner).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

describe('auth-cp-token', () => {
  it('parses user id from CP HMAC token layout', () => {
    const token = buildCpTestToken(Math.floor(Date.now() / 1000) + 3600);
    expect(parseCpAuthTokenUserId(token)).toBe('user_test');
  });

  it('rejects expired CP token', () => {
    const token = buildCpTestToken(Math.floor(Date.now() / 1000) - 60);
    expect(isCpAuthTokenValid(token)).toBe(false);
  });
});

describe('hasCpMarketplaceJwt', () => {
  it('rejects local-only token', () => {
    expect(hasCpMarketplaceJwt('local_user_token')).toBe(false);
  });

  it('rejects empty token', () => {
    expect(hasCpMarketplaceJwt(null)).toBe(false);
    expect(hasCpMarketplaceJwt('')).toBe(false);
  });

  it('rejects malformed token', () => {
    expect(hasCpMarketplaceJwt('not-a-cp-token')).toBe(false);
  });

  it('rejects expired CP token', () => {
    expect(hasCpMarketplaceJwt(buildCpTestToken(Math.floor(Date.now() / 1000) - 60))).toBe(false);
  });

  it('accepts non-expired CP token', () => {
    expect(hasCpMarketplaceJwt(buildCpTestToken(Math.floor(Date.now() / 1000) + 3600))).toBe(true);
  });
});
