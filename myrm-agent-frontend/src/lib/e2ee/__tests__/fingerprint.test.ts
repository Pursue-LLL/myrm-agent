import { describe, expect, it } from 'vitest';
import nacl from 'tweetnacl';
import { computeE2EEFingerprint, computeE2EEFingerprintFromB64 } from '../fingerprint';

describe('computeE2EEFingerprint', () => {
  it('returns 16 hex chars grouped in 4-char blocks', () => {
    const keyPair = nacl.box.keyPair();
    const fp = computeE2EEFingerprint(keyPair.publicKey);

    expect(fp).toMatch(/^[0-9a-f]{4}( [0-9a-f]{4}){3}$/);
  });

  it('is deterministic for the same key', () => {
    const key = nacl.box.keyPair().publicKey;
    expect(computeE2EEFingerprint(key)).toBe(computeE2EEFingerprint(key));
  });

  it('produces different fingerprints for different keys', () => {
    const fp1 = computeE2EEFingerprint(nacl.box.keyPair().publicKey);
    const fp2 = computeE2EEFingerprint(nacl.box.keyPair().publicKey);
    expect(fp1).not.toBe(fp2);
  });

  it('handles a known input vector', () => {
    const zeros = new Uint8Array(32);
    const hash = nacl.hash(zeros);
    const expected = Array.from(hash.slice(0, 8))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
    const expectedGrouped = expected.replace(/(.{4})/g, '$1 ').trim();

    expect(computeE2EEFingerprint(zeros)).toBe(expectedGrouped);
  });
});

describe('computeE2EEFingerprintFromB64', () => {
  it('decodes URL-safe base64 and produces matching fingerprint', () => {
    const key = nacl.box.keyPair().publicKey;
    const b64 = btoa(String.fromCharCode(...key))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/g, '');

    expect(computeE2EEFingerprintFromB64(b64)).toBe(computeE2EEFingerprint(key));
  });

  it('handles standard base64 with padding', () => {
    const key = nacl.box.keyPair().publicKey;
    const b64 = btoa(String.fromCharCode(...key));

    expect(computeE2EEFingerprintFromB64(b64)).toBe(computeE2EEFingerprint(key));
  });
});
