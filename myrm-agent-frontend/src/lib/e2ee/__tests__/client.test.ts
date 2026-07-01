/**
 * @vitest-environment node
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import nacl from 'tweetnacl';
import {
  decodeUrlBase64,
  E2EEHandshakeRequiredError,
  loadStoredE2EESession,
  storeE2EESession,
  readServerPublicKeyFromLocation,
  appendE2EEFragment,
  e2eeRequestHeaders,
  encryptPairToken,
  encryptJsonBody,
  decryptJsonPayload,
  decryptSseFrame,
  type E2EEClientSession,
} from '../client';

describe('decodeUrlBase64', () => {
  it('decodes URL-safe base64 (no padding, - and _)', () => {
    const original = new Uint8Array([255, 254, 253, 0, 1, 2]);
    const b64 = btoa(String.fromCharCode(...original))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/g, '');

    const decoded = decodeUrlBase64(b64);
    expect(decoded).toEqual(original);
  });

  it('decodes standard base64 with padding', () => {
    const original = new Uint8Array([10, 20, 30]);
    const b64 = btoa(String.fromCharCode(...original));

    expect(decodeUrlBase64(b64)).toEqual(original);
  });

  it('handles empty string', () => {
    expect(decodeUrlBase64('')).toEqual(new Uint8Array(0));
  });

  it('roundtrips a NaCl public key', () => {
    const key = nacl.box.keyPair().publicKey;
    const b64 = btoa(String.fromCharCode(...key))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/g, '');
    expect(decodeUrlBase64(b64)).toEqual(key);
  });
});

describe('E2EEHandshakeRequiredError', () => {
  it('has correct name and default message', () => {
    const err = new E2EEHandshakeRequiredError();
    expect(err.name).toBe('E2EEHandshakeRequiredError');
    expect(err.message).toBe('E2EE handshake required but failed');
    expect(err).toBeInstanceOf(Error);
  });

  it('accepts custom message', () => {
    const err = new E2EEHandshakeRequiredError('custom');
    expect(err.message).toBe('custom');
  });
});

describe('loadStoredE2EESession / storeE2EESession', () => {
  const originalSessionStorage = globalThis.sessionStorage;
  const originalWindow = globalThis.window;

  beforeEach(() => {
    const store = new Map<string, string>();
    const mockSessionStorage = {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => {
        store.set(key, value);
      },
      removeItem: (key: string) => {
        store.delete(key);
      },
      clear: () => {
        store.clear();
      },
    } as Storage;
    Object.defineProperty(globalThis, 'sessionStorage', {
      configurable: true,
      value: mockSessionStorage,
    });
    if (typeof globalThis.window === 'undefined') {
      Object.defineProperty(globalThis, 'window', {
        configurable: true,
        value: { sessionStorage: mockSessionStorage } as unknown as Window & typeof globalThis,
      });
    }
  });

  afterEach(() => {
    Object.defineProperty(globalThis, 'sessionStorage', {
      configurable: true,
      value: originalSessionStorage,
    });
    if (originalWindow === undefined) {
      Object.defineProperty(globalThis, 'window', {
        configurable: true,
        value: undefined,
      });
    }
  });

  it('returns null when no session stored', () => {
    expect(loadStoredE2EESession()).toBeNull();
  });

  it('stores and loads session correctly', () => {
    const keyPair = nacl.box.keyPair();
    const session: E2EEClientSession = {
      sessionId: 'test-session-123',
      clientSecretKey: keyPair.secretKey,
      serverPublicKey: keyPair.publicKey,
    };

    storeE2EESession(session);
    const loaded = loadStoredE2EESession();

    expect(loaded).not.toBeNull();
    expect(loaded!.sessionId).toBe('test-session-123');
    expect(loaded!.clientSecretKey).toEqual(keyPair.secretKey);
    expect(loaded!.serverPublicKey).toEqual(keyPair.publicKey);
  });

  it('returns null for corrupted JSON', () => {
    sessionStorage.setItem('mobile_e2ee_session', '{invalid json');
    expect(loadStoredE2EESession()).toBeNull();
  });

  it('returns null for incomplete session data', () => {
    sessionStorage.setItem(
      'mobile_e2ee_session',
      JSON.stringify({ sessionId: 'x' }),
    );
    expect(loadStoredE2EESession()).toBeNull();
  });
});

describe('readServerPublicKeyFromLocation', () => {
  const originalWindow = globalThis.window;

  afterEach(() => {
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: originalWindow,
    });
  });

  it('returns undefined when no hash', () => {
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: { location: { hash: '' } } as Window & typeof globalThis,
    });
    expect(readServerPublicKeyFromLocation()).toBeUndefined();
  });

  it('extracts e2ee key from hash', () => {
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: {
        location: { hash: '#e2ee=abc123' },
      } as unknown as Window & typeof globalThis,
    });
    expect(readServerPublicKeyFromLocation()).toBe('abc123');
  });
});

describe('appendE2EEFragment', () => {
  it('appends e2ee fragment to URL', () => {
    const result = appendE2EEFragment('https://example.com/path', 'key123');
    expect(result).toBe('https://example.com/path#e2ee=key123');
  });

  it('replaces existing fragment', () => {
    const result = appendE2EEFragment('https://example.com/path#old', 'key');
    expect(result).toBe('https://example.com/path#e2ee=key');
  });
});

describe('e2eeRequestHeaders', () => {
  it('returns correct headers with session ID', () => {
    const session: E2EEClientSession = {
      sessionId: 'sess-abc',
      clientSecretKey: new Uint8Array(32),
      serverPublicKey: new Uint8Array(32),
    };
    const headers = e2eeRequestHeaders(session);
    expect(headers['X-E2EE-Session']).toBe('sess-abc');
    expect(headers['Content-Type']).toBe('application/e2ee+json');
  });
});

function makeE2EEPair(): { client: E2EEClientSession; server: E2EEClientSession } {
  const clientKp = nacl.box.keyPair();
  const serverKp = nacl.box.keyPair();
  return {
    client: {
      sessionId: 'test-session',
      clientSecretKey: new Uint8Array(clientKp.secretKey),
      serverPublicKey: new Uint8Array(serverKp.publicKey),
    },
    server: {
      sessionId: 'test-session',
      clientSecretKey: new Uint8Array(serverKp.secretKey),
      serverPublicKey: new Uint8Array(clientKp.publicKey),
    },
  };
}

describe('encryptPairToken / decryptJsonPayload roundtrip', () => {
  it('encrypts a pair token that can be decrypted by the server', () => {
    const { client, server } = makeE2EEPair();
    const token = 'my-secret-pair-token-12345';
    const encrypted = encryptPairToken(client, token);

    expect(typeof encrypted).toBe('string');
    expect(encrypted).not.toBe(token);
    expect(encrypted.length).toBeGreaterThan(0);

    const bundle = decodeUrlBase64(encrypted);
    const nonce = bundle.slice(0, nacl.box.nonceLength);
    const cipher = bundle.slice(nacl.box.nonceLength);
    const plain = nacl.box.open(cipher, nonce, server.serverPublicKey, server.clientSecretKey);
    expect(plain).not.toBeNull();
    expect(new TextDecoder().decode(plain!)).toBe(token);
  });
});

describe('encryptJsonBody / decryptJsonPayload', () => {
  it('roundtrips JSON body through encrypt → decrypt', () => {
    const { client, server } = makeE2EEPair();
    const body = JSON.stringify({ message: 'Hello, E2EE!', count: 42 });

    const encrypted = encryptJsonBody(client, body);
    const parsed = JSON.parse(encrypted) as { v: number; c: string };
    expect(parsed.v).toBe(1);
    expect(typeof parsed.c).toBe('string');

    const decrypted = decryptJsonPayload(server, parsed);
    expect(decrypted).toEqual({ message: 'Hello, E2EE!', count: 42 });
  });

  it('returns non-object payloads unchanged', () => {
    const { server } = makeE2EEPair();
    expect(decryptJsonPayload(server, null)).toBeNull();
    expect(decryptJsonPayload(server, 'string')).toBe('string');
    expect(decryptJsonPayload(server, 42)).toBe(42);
  });

  it('returns objects without c field unchanged', () => {
    const { server } = makeE2EEPair();
    const payload = { data: 'unencrypted' };
    expect(decryptJsonPayload(server, payload)).toEqual(payload);
  });
});

describe('decryptSseFrame', () => {
  it('decrypts a valid SSE frame', () => {
    const { client, server } = makeE2EEPair();
    const originalData = 'SSE event data payload';
    const encrypted = encryptJsonBody(client, JSON.stringify(originalData));
    const frame = JSON.parse(encrypted) as { c: string };
    const sseData = JSON.stringify({ c: frame.c });

    const decrypted = decryptSseFrame(server, sseData);
    expect(JSON.parse(decrypted)).toBe(originalData);
  });

  it('throws on frame without c field', () => {
    const { server } = makeE2EEPair();
    expect(() => decryptSseFrame(server, JSON.stringify({ data: 'no-c' }))).toThrow(
      'Invalid E2EE SSE frame',
    );
  });

  it('throws on invalid ciphertext', () => {
    const { server } = makeE2EEPair();
    expect(() =>
      decryptSseFrame(server, JSON.stringify({ c: 'invalid-base64-cipher' })),
    ).toThrow();
  });
});
