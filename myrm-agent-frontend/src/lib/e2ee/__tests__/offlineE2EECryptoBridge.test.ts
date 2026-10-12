import { describe, it, expect, beforeEach } from 'vitest';
import {
  encryptStagingPayload,
  decryptStagingPayload,
  getOrCreateDeviceStagingSeed,
  type StagingItemPayload,
} from '../offlineE2EECryptoBridge';

describe('offlineE2EECryptoBridge', () => {
  const samplePayload: StagingItemPayload = {
    title: 'Secret Meeting Reflection',
    content: 'Discussed architectural refactoring and offline E2EE design.',
    voiceTranscript: 'Draft note on offline first sync.',
    tags: ['design', 'security'],
    attachments: [
      {
        name: 'sketch.png',
        mimeType: 'image/png',
        dataUrl: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
        size: 68,
      },
    ],
  };

  beforeEach(() => {
    localStorage.clear();
  });

  it('generates and persists a stable device staging seed', () => {
    const seed1 = getOrCreateDeviceStagingSeed();
    expect(seed1).toBeDefined();
    expect(typeof seed1).toBe('string');
    expect(seed1.length).toBeGreaterThan(16);

    const seed2 = getOrCreateDeviceStagingSeed();
    expect(seed2).toBe(seed1);
  });

  it('encrypts and successfully decrypts payload with device default seed', async () => {
    const envelope = await encryptStagingPayload(samplePayload);

    expect(envelope.version).toBe(1);
    expect(envelope.algorithm).toBe('AES-GCM-256');
    expect(envelope.iv).toBeDefined();
    expect(envelope.salt).toBeDefined();
    expect(envelope.ciphertext).toBeDefined();

    // Verify ciphertext is not plaintext
    expect(envelope.ciphertext).not.toContain(samplePayload.content);

    const decrypted = await decryptStagingPayload(envelope);
    expect(decrypted).toEqual(samplePayload);
  });

  it('encrypts and successfully decrypts payload with custom passphrase', async () => {
    const customPassphrase = 'user-high-entropy-master-password-1234!';
    const envelope = await encryptStagingPayload(samplePayload, customPassphrase);
    const decrypted = await decryptStagingPayload(envelope, customPassphrase);

    expect(decrypted).toEqual(samplePayload);
  });

  it('fails decryption when custom passphrase is wrong', async () => {
    const envelope = await encryptStagingPayload(samplePayload, 'correct-passphrase');

    await expect(decryptStagingPayload(envelope, 'wrong-passphrase')).rejects.toThrow();
  });

  it('produces unique IVs and ciphertexts for identical payloads across multiple encryptions', async () => {
    const envelope1 = await encryptStagingPayload(samplePayload, 'pass-1');
    const envelope2 = await encryptStagingPayload(samplePayload, 'pass-1');

    expect(envelope1.iv).not.toBe(envelope2.iv);
    expect(envelope1.salt).not.toBe(envelope2.salt);
    expect(envelope1.ciphertext).not.toBe(envelope2.ciphertext);
  });
});
