import { vi } from 'vitest';

import type { E2EEClientSession } from '@/lib/e2ee/client';

export const BACKEND = 'http://backend.test';

/** A fixed, whole-second "now" so token expiry arithmetic is exact. */
export const NOW = Date.UTC(2026, 0, 1);

export const SESSION: E2EEClientSession = {
  sessionId: 'session-1',
  clientSecretKey: new Uint8Array([1]),
  serverPublicKey: new Uint8Array([2]),
};

const hoisted = vi.hoisted(() => ({
  loadStoredE2EESession: vi.fn<() => E2EEClientSession | null>(),
  readServerPublicKeyFromLocation: vi.fn<() => string | undefined>(),
  ensureE2EEHandshake: vi.fn<(baseUrl: string) => Promise<E2EEClientSession | null>>(),
  e2eeRequestHeaders: vi.fn<(session: E2EEClientSession) => Record<string, string>>(),
  encryptPairToken: vi.fn<(session: E2EEClientSession, token: string) => string>(),
  encryptJsonBody: vi.fn<(session: E2EEClientSession, body: string) => string>(),
  decryptJsonPayload: vi.fn<(session: E2EEClientSession, payload: unknown) => unknown>(),
}));

export { hoisted as kit };

/** The E2EE client with its session and crypto entry points replaced; the error class and base64 helper stay real. */
export async function e2eeClientMock() {
  const actual = await vi.importActual<typeof import('@/lib/e2ee/client')>('@/lib/e2ee/client');
  return { ...actual, ...hoisted };
}

export const apiConfigMock = () => ({ getBackendUrl: () => BACKEND });

/** A pair token as the server issues it: URL-safe base64 of the JSON payload, a dot, then the signature. */
export function pairToken(payload: Record<string, unknown>, signature = 'sig'): string {
  const body = btoa(JSON.stringify(payload)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  return `${body}.${signature}`;
}

/** A pair token that expires `seconds` after the current (possibly faked) time. */
export const tokenExpiringIn = (seconds: number): string => pairToken({ exp: Date.now() / 1000 + seconds });

/** The part of a fetch answer the client reads. */
export function jsonResponse(body: unknown, status = 200): Response {
  const answer: Pick<Response, 'ok' | 'status' | 'json'> = {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  };
  return answer as Response;
}
