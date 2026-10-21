import nacl from 'tweetnacl';

export type E2EEClientSession = {
  sessionId: string;
  clientSecretKey: Uint8Array;
  serverPublicKey: Uint8Array;
};

const E2EE_SESSION_STORAGE_KEY = 'mobile_e2ee_session';
const E2EE_SERVER_PUB_FRAGMENT = 'e2ee';

function encodeStandardBase64(bytes: Uint8Array): string {
  let binary = '';
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary);
}

function decodeStandardBase64(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

export function decodeUrlBase64(value: string): Uint8Array {
  const padded = value + '='.repeat((4 - (value.length % 4)) % 4);
  const normalized = padded.replace(/-/g, '+').replace(/_/g, '/');
  const binary = atob(normalized);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

function encodeUrlBase64(bytes: Uint8Array): string {
  return encodeStandardBase64(bytes).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

export class E2EEHandshakeRequiredError extends Error {
  constructor(message = 'E2EE handshake required but failed') {
    super(message);
    this.name = 'E2EEHandshakeRequiredError';
  }
}

export function readServerPublicKeyFromLocation(): string | undefined {
  if (typeof window === 'undefined') {
    return undefined;
  }
  const hash = window.location.hash.replace(/^#/, '');
  if (!hash) {
    return undefined;
  }
  const params = new URLSearchParams(hash);
  const value = params.get(E2EE_SERVER_PUB_FRAGMENT);
  return value ?? undefined;
}

export function appendE2EEFragment(url: string, serverPublicKeyB64: string): string {
  const base = url.split('#')[0] ?? url;
  return `${base}#${E2EE_SERVER_PUB_FRAGMENT}=${encodeURIComponent(serverPublicKeyB64)}`;
}

export function loadStoredE2EESession(): E2EEClientSession | null {
  if (typeof window === 'undefined') {
    return null;
  }
  const raw = sessionStorage.getItem(E2EE_SESSION_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as {
      sessionId?: string;
      clientSecretKeyB64?: string;
      serverPublicKeyB64?: string;
    };
    if (!parsed.sessionId || !parsed.clientSecretKeyB64 || !parsed.serverPublicKeyB64) {
      return null;
    }
    return {
      sessionId: parsed.sessionId,
      clientSecretKey: decodeStandardBase64(parsed.clientSecretKeyB64),
      serverPublicKey: decodeStandardBase64(parsed.serverPublicKeyB64),
    };
  } catch {
    return null;
  }
}

export function storeE2EESession(session: E2EEClientSession): void {
  if (typeof window === 'undefined') {
    return;
  }
  sessionStorage.setItem(
    E2EE_SESSION_STORAGE_KEY,
    JSON.stringify({
      sessionId: session.sessionId,
      clientSecretKeyB64: encodeStandardBase64(session.clientSecretKey),
      serverPublicKeyB64: encodeStandardBase64(session.serverPublicKey),
    }),
  );
}

function sealText(session: E2EEClientSession, plaintext: string): string {
  const nonce = nacl.randomBytes(nacl.box.nonceLength);
  const message = new TextEncoder().encode(plaintext);
  const cipher = nacl.box(message, nonce, session.serverPublicKey, session.clientSecretKey);
  if (!cipher) {
    throw new Error('E2EE encryption failed');
  }
  const bundle = new Uint8Array(nonce.length + cipher.length);
  bundle.set(nonce, 0);
  bundle.set(cipher, nonce.length);
  return encodeUrlBase64(bundle);
}

function openText(session: E2EEClientSession, bundleB64: string): string {
  const bundle = decodeUrlBase64(bundleB64);
  const nonce = bundle.slice(0, nacl.box.nonceLength);
  const cipher = bundle.slice(nacl.box.nonceLength);
  const plain = nacl.box.open(cipher, nonce, session.serverPublicKey, session.clientSecretKey);
  if (!plain) {
    throw new Error('E2EE decryption failed');
  }
  return new TextDecoder().decode(plain);
}

export async function ensureE2EEHandshake(baseUrl: string): Promise<E2EEClientSession | null> {
  const existing = loadStoredE2EESession();
  if (existing) {
    return existing;
  }
  const serverPublicKeyB64 = readServerPublicKeyFromLocation();
  if (!serverPublicKeyB64) {
    return null;
  }
  const clientKeyPair = nacl.box.keyPair();
  const response = await fetch(`${baseUrl}/api/v1/remote-access/e2ee/handshake`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      type: 'e2ee_hello',
      key: encodeUrlBase64(clientKeyPair.publicKey),
    }),
  });
  if (!response.ok) {
    return null;
  }
  const payload = (await response.json()) as {
    data?: { sessionId?: string; serverPublicKeyB64?: string; type?: string };
  };
  const sessionId = payload.data?.sessionId;
  const confirmedServerKey = payload.data?.serverPublicKeyB64 ?? serverPublicKeyB64;
  if (!sessionId || payload.data?.type !== 'e2ee_ready') {
    return null;
  }
  const session: E2EEClientSession = {
    sessionId,
    clientSecretKey: clientKeyPair.secretKey,
    serverPublicKey: decodeUrlBase64(confirmedServerKey),
  };
  storeE2EESession(session);
  return session;
}

export function encryptPairToken(session: E2EEClientSession, pairToken: string): string {
  return sealText(session, pairToken);
}

export function encryptJsonBody(session: E2EEClientSession, body: string): string {
  return JSON.stringify({ v: 1, c: sealText(session, body) });
}

export function decryptJsonPayload(session: E2EEClientSession, payload: unknown): unknown {
  if (!payload || typeof payload !== 'object') {
    return payload;
  }
  const record = payload as { c?: string };
  if (typeof record.c !== 'string') {
    return payload;
  }
  const plain = openText(session, record.c);
  return JSON.parse(plain) as unknown;
}

export function e2eeRequestHeaders(session: E2EEClientSession): Record<string, string> {
  return {
    'X-E2EE-Session': session.sessionId,
    'Content-Type': 'application/e2ee+json',
  };
}

export function decryptSseFrame(session: E2EEClientSession, data: string): string {
  const payload = JSON.parse(data) as { c?: string };
  if (typeof payload.c !== 'string') {
    throw new Error('Invalid E2EE SSE frame');
  }
  return openText(session, payload.c);
}
