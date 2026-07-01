import nacl from 'tweetnacl';

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
  const padded = publicKeyB64 + '='.repeat((4 - (publicKeyB64.length % 4)) % 4);
  const normalized = padded.replace(/-/g, '+').replace(/_/g, '/');
  const binary = atob(normalized);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return computeE2EEFingerprint(bytes);
}
