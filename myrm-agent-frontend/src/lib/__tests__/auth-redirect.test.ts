import { describe, expect, it } from 'vitest';
import {
  authRedirectQueryParam,
  buildAuthLoginPath,
  readAuthRedirectParam,
  sanitizeAuthRedirectPath,
} from '@/lib/auth-redirect';

describe('auth-redirect', () => {
  it('allows safe internal paths', () => {
    expect(sanitizeAuthRedirectPath('/settings')).toBe('/settings');
    expect(sanitizeAuthRedirectPath('/chat?agent=1')).toBe('/chat?agent=1');
  });

  it('blocks open redirects', () => {
    expect(sanitizeAuthRedirectPath('https://evil.com')).toBeNull();
    expect(sanitizeAuthRedirectPath('//evil.com')).toBeNull();
    expect(sanitizeAuthRedirectPath('')).toBeNull();
    expect(sanitizeAuthRedirectPath(null)).toBeNull();
  });

  it('buildAuthLoginPath omits redirect for home', () => {
    expect(buildAuthLoginPath('/')).toBe('/auth/login');
    expect(buildAuthLoginPath(null)).toBe('/auth/login');
  });

  it('buildAuthLoginPath preserves post-auth return target', () => {
    expect(buildAuthLoginPath('/subscription')).toBe(
      `/auth/login?${authRedirectQueryParam('/subscription')}`,
    );
  });

  it('readAuthRedirectParam round-trips through URLSearchParams', () => {
    const params = new URLSearchParams(authRedirectQueryParam('/memory'));
    expect(readAuthRedirectParam(params)).toBe('/memory');
  });
});
