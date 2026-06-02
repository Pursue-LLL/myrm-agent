import { createHmac } from 'crypto';
import { describe, expect, it } from 'vitest';
import { parseCpAuthTokenUserId } from '@/lib/auth-cp-token';

/** Mirrors myrm_control_plane.auth.tokens.generate_api_token for tests. */
function generateCpAuthToken(userId: string, secret: string, ttlSeconds = 3600): string {
  const expiry = Math.floor(Date.now() / 1000) + ttlSeconds;
  const payload = `${userId}:${expiry}`;
  const signature = createHmac('sha256', secret).update(payload).digest();
  const sigB64 = signature.toString('base64url');
  const inner = `${payload}.${sigB64}`;
  return Buffer.from(inner).toString('base64url');
}

describe('parseCpAuthTokenUserId', () => {
  it('extracts user id from control-plane HMAC tokens', () => {
    const token = generateCpAuthToken('user-saas-42', 'test-secret');
    expect(parseCpAuthTokenUserId(token)).toBe('user-saas-42');
  });

  it('returns null for malformed tokens', () => {
    expect(parseCpAuthTokenUserId('')).toBeNull();
    expect(parseCpAuthTokenUserId('not-valid')).toBeNull();
  });
});
