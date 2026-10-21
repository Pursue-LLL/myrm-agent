/**
 * [INPUT]
 * - Web Crypto unavailable — decode-only, matches CP HMAC token layout (no secret on client)
 *
 * [OUTPUT]
 * - parseCpAuthTokenUserId, isCpAuthTokenValid
 *
 * [POS]
 * Client-side parser for control-plane HMAC API tokens (generate_api_token format).
 */

type DecodedCpAuthToken = {
  userId: string;
  expirySeconds: number;
};

function decodeCpAuthToken(token: string): DecodedCpAuthToken | null {
  try {
    const normalized = token.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized + '='.repeat((4 - (normalized.length % 4)) % 4);
    const decoded = atob(padded);
    const payloadPart = decoded.split('.')[0];
    const separator = payloadPart.indexOf(':');
    if (separator <= 0) {
      return null;
    }
    const userId = payloadPart.slice(0, separator);
    const expirySeconds = Number.parseInt(payloadPart.slice(separator + 1), 10);
    if (!userId || !Number.isFinite(expirySeconds)) {
      return null;
    }
    return { userId, expirySeconds };
  } catch {
    return null;
  }
}

export function parseCpAuthTokenUserId(token: string): string | null {
  return decodeCpAuthToken(token)?.userId ?? null;
}

/** True when token decodes as CP HMAC API token and expiry is in the future. */
export function isCpAuthTokenValid(token: string, nowMs: number = Date.now()): boolean {
  const decoded = decodeCpAuthToken(token);
  if (!decoded) {
    return false;
  }
  return decoded.expirySeconds * 1000 > nowMs;
}
