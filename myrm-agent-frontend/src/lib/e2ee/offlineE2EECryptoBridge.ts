/**
 * [INPUT]
 * - Web Crypto API (SubtleCrypto: AES-GCM-256, PBKDF2)
 *
 * [OUTPUT]
 * - encryptStagingPayload: client-side AES-GCM-256 envelope encryption
 * - decryptStagingPayload: authenticated decryption and payload recovery
 * - derivePassphraseKey: PBKDF2 key derivation for zero-knowledge note secrecy
 *
 * [POS]
 * Client-side end-to-end encryption bridge for mobile quick capture and offline staging.
 * Ensures user captured notes and confidential reflections are encrypted before persisting
 * to local IndexedDB or synchronizing over untrusted networks.
 */

export interface StagingAttachment {
  name: string;
  mimeType: string;
  dataUrl: string;
  size: number;
}

export interface StagingItemPayload {
  title?: string;
  content: string;
  voiceTranscript?: string;
  attachments?: StagingAttachment[];
  tags?: string[];
  chatId?: string;
}

export interface EncryptedStagingEnvelope {
  version: 1;
  algorithm: 'AES-GCM-256';
  iv: string; // Base64 encoded 12-byte IV
  salt: string; // Base64 encoded 16-byte salt
  ciphertext: string; // Base64 encoded ciphertext
  createdAt: number;
}

const DEFAULT_DEVICE_STAGING_KEY_STORAGE = 'myrm_device_e2ee_staging_seed';

function arrayBufferToBase64(buffer: ArrayBuffer | Uint8Array): string {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function base64ToArrayBuffer(base64: string): Uint8Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

function getSubtleCrypto(): SubtleCrypto {
  if (typeof window !== 'undefined' && window.crypto && window.crypto.subtle) {
    return window.crypto.subtle;
  }
  if (typeof globalThis !== 'undefined' && globalThis.crypto && globalThis.crypto.subtle) {
    return globalThis.crypto.subtle;
  }
  throw new Error('Web Crypto API SubtleCrypto is not supported in current environment');
}

export function getOrCreateDeviceStagingSeed(): string {
  if (typeof window === 'undefined' || !window.localStorage) {
    return 'ephemeral_fallback_seed_for_non_browser_environments';
  }
  let seed = localStorage.getItem(DEFAULT_DEVICE_STAGING_KEY_STORAGE);
  if (!seed) {
    const randomBytes = new Uint8Array(32);
    if (window.crypto?.getRandomValues) {
      window.crypto.getRandomValues(randomBytes);
    } else {
      for (let i = 0; i < 32; i += 1) {
        randomBytes[i] = Math.floor(Math.random() * 256);
      }
    }
    seed = arrayBufferToBase64(randomBytes);
    localStorage.setItem(DEFAULT_DEVICE_STAGING_KEY_STORAGE, seed);
  }
  return seed;
}

export async function derivePassphraseKey(passphrase: string, salt: Uint8Array): Promise<CryptoKey> {
  const subtle = getSubtleCrypto();
  const encoder = new TextEncoder();
  const rawKey = encoder.encode(passphrase);

  const baseKey = await subtle.importKey(
    'raw',
    rawKey,
    { name: 'PBKDF2' },
    false,
    ['deriveKey'],
  );

  return subtle.deriveKey(
    {
      name: 'PBKDF2',
      salt: salt as unknown as BufferSource,
      iterations: 100_000,
      hash: 'SHA-256',
    },
    baseKey,
    {
      name: 'AES-GCM',
      length: 256,
    },
    false,
    ['encrypt', 'decrypt'],
  );
}

export async function encryptStagingPayload(
  payload: StagingItemPayload,
  customPassphrase?: string,
): Promise<EncryptedStagingEnvelope> {
  const subtle = getSubtleCrypto();
  const passphrase = customPassphrase || getOrCreateDeviceStagingSeed();

  const salt = new Uint8Array(16);
  const iv = new Uint8Array(12);

  if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
    crypto.getRandomValues(salt);
    crypto.getRandomValues(iv);
  } else {
    for (let i = 0; i < 16; i += 1) {
      salt[i] = Math.floor(Math.random() * 256);
    }
    for (let i = 0; i < 12; i += 1) {
      iv[i] = Math.floor(Math.random() * 256);
    }
  }

  const cryptoKey = await derivePassphraseKey(passphrase, salt);
  const plaintext = JSON.stringify(payload);
  const encodedPlaintext = new TextEncoder().encode(plaintext);

  const encryptedBuffer = await subtle.encrypt(
    {
      name: 'AES-GCM',
      iv: iv as unknown as BufferSource,
    },
    cryptoKey,
    encodedPlaintext,
  );

  return {
    version: 1,
    algorithm: 'AES-GCM-256',
    iv: arrayBufferToBase64(iv),
    salt: arrayBufferToBase64(salt),
    ciphertext: arrayBufferToBase64(encryptedBuffer),
    createdAt: Date.now(),
  };
}

export async function decryptStagingPayload(
  envelope: EncryptedStagingEnvelope,
  customPassphrase?: string,
): Promise<StagingItemPayload> {
  const subtle = getSubtleCrypto();
  const passphrase = customPassphrase || getOrCreateDeviceStagingSeed();

  const salt = base64ToArrayBuffer(envelope.salt);
  const iv = base64ToArrayBuffer(envelope.iv);
  const ciphertext = base64ToArrayBuffer(envelope.ciphertext);

  const cryptoKey = await derivePassphraseKey(passphrase, salt);

  const decryptedBuffer = await subtle.decrypt(
    {
      name: 'AES-GCM',
      iv: iv as unknown as BufferSource,
    },
    cryptoKey,
    ciphertext as unknown as BufferSource,
  );

  const plaintext = new TextDecoder().decode(decryptedBuffer);
  return JSON.parse(plaintext) as StagingItemPayload;
}
