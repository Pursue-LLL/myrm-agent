const MOBILE_PAIR_STORAGE_KEY = 'mobile_pair_token';

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
