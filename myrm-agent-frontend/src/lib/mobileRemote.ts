import { getBackendUrl } from '@/lib/utils/apiConfig';

const MOBILE_PAIR_STORAGE_KEY = 'mobile_pair_token';
const PAIR_REFRESH_LEAD_MS = 5 * 60 * 1000;

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

export function withMobilePairHeaders(headers: Record<string, string> = {}): Record<string, string> {
  const pair = getMobilePairToken();
  if (!pair) {
    return headers;
  }
  return { ...headers, 'X-Pair-Token': pair };
}

export function buildMobileHubUrl(
  mobilePath: string,
  tunnelPublicUrl: string,
  ingressBaseUrl: string,
): string {
  const base = tunnelPublicUrl || ingressBaseUrl || (typeof window !== 'undefined' ? window.location.origin : '');
  if (!base) {
    return mobilePath;
  }
  const normalizedPath = mobilePath.startsWith('/') ? mobilePath : `/${mobilePath}`;
  return `${base.replace(/\/$/, '')}${normalizedPath}`;
}

export async function refreshMobilePairToken(): Promise<string | undefined> {
  const current = getMobilePairToken();
  if (!current) {
    return undefined;
  }
  const response = await fetch(`${getBackendUrl()}/api/v1/remote-access/pairing-token/refresh`, {
    method: 'POST',
    headers: withMobilePairHeaders({ 'Content-Type': 'application/json' }),
    credentials: 'include',
  });
  if (!response.ok) {
    return undefined;
  }
  const payload = (await response.json()) as { data?: { token?: string } };
  const token = payload.data?.token;
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
