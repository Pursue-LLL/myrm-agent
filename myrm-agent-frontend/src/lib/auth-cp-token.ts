/**
 * Parse user id from control-plane HMAC API tokens (client-side, no secret).
 * Format matches myrm_control_plane.auth.tokens.generate_api_token.
 */

export function parseCpAuthTokenUserId(token: string): string | null {
  try {
    const normalized = token.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized + '='.repeat((4 - (normalized.length % 4)) % 4);
    const decoded = atob(padded);
    const payload = decoded.split('.')[0];
    const userId = payload.split(':')[0];
    return userId || null;
  } catch {
    return null;
  }
}
