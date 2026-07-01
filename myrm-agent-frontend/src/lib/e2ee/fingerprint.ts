import nacl from 'tweetnacl';
import { decodeUrlBase64 } from '@/lib/e2ee/client';

/**
 * Compute a human-readable fingerprint from a raw public key using SHA-512.
 * Returns the first 16 hex characters grouped in 4-char blocks (e.g. "a1b2 c3d4 e5f6 g7h8").
 */
export function computeE2EEFingerprint(publicKey: Uint8Array): string {
  const hash = nacl.hash(publicKey);
  const hex = Array.from(hash.slice(0, 8))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
  return hex.replace(/(.{4})/g, '$1 ').trim();
}

/**
 * Compute fingerprint from a URL-safe or standard base64-encoded public key.
 */
export function computeE2EEFingerprintFromB64(publicKeyB64: string): string {
  return computeE2EEFingerprint(decodeUrlBase64(publicKeyB64));
}
