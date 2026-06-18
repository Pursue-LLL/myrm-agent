import { getBackendUrl } from '@/lib/utils/apiConfig';
import {
  decryptJsonPayload,
  E2EEHandshakeRequiredError,
  e2eeRequestHeaders,
  encryptJsonBody,
  encryptPairToken,
  ensureE2EEHandshake,
  loadStoredE2EESession,
  readServerPublicKeyFromLocation,
  type E2EEClientSession,
} from '@/lib/e2ee/client';

const MOBILE_PAIR_STORAGE_KEY = 'mobile_pair_token';
const PAIR_REFRESH_LEAD_MS = 5 * 60 * 1000;

type PairingTokenResponse = {
  token: string;
  mobilePath?: string;
};

export function isMobileRemoteSurface(): boolean {
  return typeof window !== 'undefined' && window.location.pathname.startsWith('/mobile');
}

function stripPairTokenFromUrl(): void {
  if (typeof window === 'undefined') {
    return;
  }
  const params = new URLSearchParams(window.location.search);
  if (!params.has('pair')) {
    return;
  }
  params.delete('pair');
  const query = params.toString();
  const nextUrl = `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`;
  window.history.replaceState(null, '', nextUrl);
}

type PairTokenPayload = {
  chat_id?: string | null;
  purpose?: string;
  exp?: number;
};

function decodePairPayload(token: string): PairTokenPayload | null {
  const [bodyB64] = token.split('.');
  if (!bodyB64) {
    return null;
  }
  try {
    const padded = bodyB64 + '='.repeat((4 - (bodyB64.length % 4)) % 4);
    const json = atob(padded.replace(/-/g, '+').replace(/_/g, '/'));
    return JSON.parse(json) as PairTokenPayload;
  } catch {
    return null;
  }
}

export function getMobilePairToken(): string | undefined {
  if (typeof window === 'undefined') {
    return undefined;
  }
  const fromUrl = new URLSearchParams(window.location.search).get('pair');
  if (fromUrl) {
    sessionStorage.setItem(MOBILE_PAIR_STORAGE_KEY, fromUrl);
    stripPairTokenFromUrl();
    return fromUrl;
  }
  const stored = sessionStorage.getItem(MOBILE_PAIR_STORAGE_KEY);
  return stored ?? undefined;
}

export function storeMobilePairToken(token: string): void {
  if (typeof window === 'undefined') {
    return;
  }
  sessionStorage.setItem(MOBILE_PAIR_STORAGE_KEY, token);
}

export async function ensureMobileE2EE(): Promise<E2EEClientSession | null> {
  const existing = loadStoredE2EESession();
  if (existing) {
    return existing;
  }
  const serverPublicKeyB64 = readServerPublicKeyFromLocation();
  if (!serverPublicKeyB64) {
    return null;
  }
  const session = await ensureE2EEHandshake(getBackendUrl());
  if (!session) {
    throw new E2EEHandshakeRequiredError();
  }
  return session;
}

export function withMobilePairHeaders(headers: Record<string, string> = {}): Record<string, string> {
  const pair = getMobilePairToken();
  const session = loadStoredE2EESession();
  const merged = { ...headers };
  if (session) {
    Object.assign(merged, e2eeRequestHeaders(session));
  }
  if (!pair) {
    return merged;
  }
  if (session) {
    merged['X-E2EE-Pair-Token'] = encryptPairToken(session, pair);
    return merged;
  }
  if (readServerPublicKeyFromLocation()) {
    throw new E2EEHandshakeRequiredError();
  }
  return { ...merged, 'X-Pair-Token': pair };
}

export function buildMobileHubUrl(
  mobilePath: string,
  tunnelPublicUrl: string,
  ingressBaseUrl: string,
  serverPublicKeyB64?: string,
): string {
  const base = tunnelPublicUrl || ingressBaseUrl || (typeof window !== 'undefined' ? window.location.origin : '');
  if (!base) {
    return mobilePath;
  }
  const normalizedPath = mobilePath.startsWith('/') ? mobilePath : `/${mobilePath}`;
  const url = `${base.replace(/\/$/, '')}${normalizedPath}`;
  if (!serverPublicKeyB64) {
    return url;
  }
  return `${url.split('#')[0]}#e2ee=${encodeURIComponent(serverPublicKeyB64)}`;
}

async function mobileFetch(path: string, init: RequestInit = {}): Promise<Response> {
  await ensureMobileE2EE();
  const headers = withMobilePairHeaders(
    init.headers instanceof Headers
      ? Object.fromEntries(init.headers.entries())
      : (init.headers as Record<string, string> | undefined) ?? {},
  );
  const session = loadStoredE2EESession();
  let body = init.body;
  if (session && typeof body === 'string' && body.length > 0) {
    body = encryptJsonBody(session, body);
  }
  return fetch(`${getBackendUrl()}${path}`, {
    ...init,
    headers,
    body,
    credentials: 'include',
  });
}

export async function mobileApiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await mobileFetch(path, init);
  if (!response.ok) {
    throw new Error(`Mobile API failed: ${response.status}`);
  }
  const payload = (await response.json()) as unknown;
  const session = loadStoredE2EESession();
  const decoded =
    session && payload && typeof payload === 'object' && 'c' in (payload as Record<string, unknown>)
      ? decryptJsonPayload(session, payload)
      : payload;
  if (decoded && typeof decoded === 'object' && decoded !== null && 'data' in decoded) {
    return (decoded as { data: T }).data;
  }
  return decoded as T;
}

export async function mobileRemotePost<T>(path: string, body: Record<string, unknown>): Promise<T> {
  return mobileApiRequest<T>(path, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function refreshMobilePairToken(): Promise<string | undefined> {
  const current = getMobilePairToken();
  if (!current) {
    return undefined;
  }
  const payload = await mobileApiRequest<PairingTokenResponse>(
    '/api/v1/remote-access/pairing-token/refresh',
    { method: 'POST' },
  );
  const token = payload.token;
  if (!token) {
    return undefined;
  }
  storeMobilePairToken(token);
  return token;
}

export function scheduleMobilePairRefresh(): () => void {
  if (typeof window === 'undefined') {
    return () => undefined;
  }

  let timer: number | undefined;

  const schedule = () => {
    if (timer !== undefined) {
      window.clearTimeout(timer);
    }
    const token = getMobilePairToken();
    if (!token) {
      return;
    }
    const payload = decodePairPayload(token);
    if (!payload?.exp) {
      return;
    }
    const refreshAt = payload.exp * 1000 - PAIR_REFRESH_LEAD_MS;
    const delay = Math.max(refreshAt - Date.now(), 30_000);
    timer = window.setTimeout(() => {
      void refreshMobilePairToken().finally(schedule);
    }, delay);
  };

  schedule();
  return () => {
    if (timer !== undefined) {
      window.clearTimeout(timer);
    }
  };
}
