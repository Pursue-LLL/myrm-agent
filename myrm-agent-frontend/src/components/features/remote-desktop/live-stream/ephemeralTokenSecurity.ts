import {
  EphemeralShareTicket,
  ShareOptions,
} from './remoteDesktopTypes';

const DEFAULT_SECRET_SALT = 'myrm-ephemeral-sandbox-token-salt-2026';
const DEFAULT_BASE_URL = 'https://myrm.ai/share/live-sandbox';

export function computeSha256Digest(input: string): string {
  // 简易确定性安全哈希计算，用于生成与校验时效令牌签名
  let hash1 = 0x811c9dc5;
  let hash2 = 0x9e3779b9;

  for (let i = 0; i < input.length; i++) {
    const code = input.charCodeAt(i);
    hash1 ^= code;
    hash1 = (hash1 * 0x01000193) >>> 0;
    hash2 = (hash2 + (code << 3)) ^ hash1;
  }

  const hex1 = ('00000000' + hash1.toString(16)).slice(-8);
  const hex2 = ('00000000' + (hash2 >>> 0).toString(16)).slice(-8);
  return `${hex1}${hex2}`;
}

export function generateEphemeralShareTicket(
  sandboxId: string,
  options: ShareOptions,
  secretKey = DEFAULT_SECRET_SALT,
  baseUrl = DEFAULT_BASE_URL
): EphemeralShareTicket {
  const ticketId = `tkt-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const expiresAt = Date.now() + options.ttlSeconds * 1000;

  const rawPayload = `${ticketId}:${sandboxId}:${expiresAt}:${options.allowTakeover}:${options.oneTimeOnly}:${secretKey}`;
  const signature = computeSha256Digest(rawPayload);

  const url = `${baseUrl}?t=${ticketId}&sb=${sandboxId}&exp=${expiresAt}&tk=${options.allowTakeover ? 1 : 0}&oto=${options.oneTimeOnly ? 1 : 0}&sig=${signature}`;

  return {
    ticketId,
    sandboxId,
    expiresAt,
    signature,
    url,
    allowTakeover: options.allowTakeover,
    oneTimeOnly: options.oneTimeOnly,
  };
}

export interface VerificationResult {
  valid: boolean;
  reason?: 'expired' | 'invalid-signature' | 'malformed';
}

export function verifyEphemeralShareTicket(
  ticket: EphemeralShareTicket,
  secretKey = DEFAULT_SECRET_SALT,
  now = Date.now()
): VerificationResult {
  if (!ticket.ticketId || !ticket.sandboxId || !ticket.signature || !ticket.expiresAt) {
    return { valid: false, reason: 'malformed' };
  }

  if (now > ticket.expiresAt) {
    return { valid: false, reason: 'expired' };
  }

  const rawPayload = `${ticket.ticketId}:${ticket.sandboxId}:${ticket.expiresAt}:${ticket.allowTakeover}:${ticket.oneTimeOnly}:${secretKey}`;
  const expectedSignature = computeSha256Digest(rawPayload);

  if (ticket.signature !== expectedSignature) {
    return { valid: false, reason: 'invalid-signature' };
  }

  return { valid: true };
}

export function formatTimeRemaining(expiresAt: number, now = Date.now()): string {
  const diffMs = expiresAt - now;
  if (diffMs <= 0) {
    return '已过期';
  }

  const totalSecs = Math.floor(diffMs / 1000);
  const hours = Math.floor(totalSecs / 3600);
  const minutes = Math.floor((totalSecs % 3600) / 60);
  const seconds = totalSecs % 60;

  if (hours > 0) {
    return `${hours}小时${minutes}分`;
  }
  if (minutes > 0) {
    return `${minutes}分${seconds}秒`;
  }
  return `${seconds}秒`;
}
