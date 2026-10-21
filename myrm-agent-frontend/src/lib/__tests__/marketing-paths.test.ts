import { describe, expect, it } from 'vitest';
import { isPetOverlayPath, isSaasPublicPath, isStandalonePath } from '@/lib/marketing-paths';

describe('marketing-paths auth routes', () => {
  it('treats OAuth callback as standalone', () => {
    expect(isStandalonePath('/auth/oauth/callback')).toBe(true);
  });

  it('treats pet overlay as standalone without AppLayout', () => {
    expect(isPetOverlayPath('/pet-overlay')).toBe(true);
    expect(isStandalonePath('/pet-overlay')).toBe(true);
  });

  it('allows OAuth callback without session cookie in SaaS middleware', () => {
    expect(isSaasPublicPath('/auth/oauth/callback')).toBe(true);
    expect(isSaasPublicPath('/chat')).toBe(false);
  });
});
