import { API_BASE_URL } from '@/lib/api';

export function buildThemeAssetContentUrl(assetRef: string): string | null {
  if (!assetRef.startsWith('file:')) {
    return null;
  }
  const fileId = assetRef.slice('file:'.length);
  if (!fileId) {
    return null;
  }
  return `${API_BASE_URL}/files/storage/files/${encodeURIComponent(fileId)}/content`;
}

export async function resolveThemeAssetUrl(
  assetRef: string | null | undefined,
): Promise<string | null> {
  if (!assetRef) {
    return null;
  }
  return buildThemeAssetContentUrl(assetRef);
}

export async function verifyThemeAssetAvailable(
  assetRef: string | null | undefined,
): Promise<boolean> {
  if (!assetRef?.startsWith('file:')) {
    return true;
  }
  const url = buildThemeAssetContentUrl(assetRef);
  if (!url) {
    return false;
  }
  try {
    const head = await fetch(url, { method: 'HEAD', credentials: 'include' });
    if (head.ok) {
      return true;
    }
    if (head.status !== 405) {
      return false;
    }
    const probe = await fetch(url, {
      method: 'GET',
      credentials: 'include',
      headers: { Range: 'bytes=0-0' },
    });
    return probe.ok || probe.status === 206;
  } catch {
    return false;
  }
}
