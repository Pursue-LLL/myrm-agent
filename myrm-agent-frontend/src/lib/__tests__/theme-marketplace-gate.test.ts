import { describe, expect, it } from 'vitest';
import { hasCpMarketplaceJwt } from '@/lib/theme-marketplace-gate';

describe('hasCpMarketplaceJwt', () => {
  it('rejects local-only token', () => {
    expect(hasCpMarketplaceJwt('local_user_token')).toBe(false);
  });

  it('rejects empty token', () => {
    expect(hasCpMarketplaceJwt(null)).toBe(false);
    expect(hasCpMarketplaceJwt('')).toBe(false);
  });

  it('accepts JWT-shaped token', () => {
    expect(hasCpMarketplaceJwt('header.payload.sig')).toBe(true);
  });
});
