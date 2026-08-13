import { BACKEND_BASE_URL, getApiUrl } from '@/lib/api';

export interface ArtifactShareRecord {
  id: string;
  artifact_id: string;
  artifact_name: string;
  artifact_type: string | null;
  password_protected: boolean;
  created_at: number;
  expires_at: number;
  share_path: string | null;
  share_url: string | null;
}

/**
 * Build the publicly reachable share URL. Server-provided absolute URLs (public
 * ingress / tunnel) pass through untouched; relative paths fall back to the
 * backend base or the current origin.
 */
export function buildPublicArtifactShareUrl(sharePath: string): string {
  if (sharePath.startsWith('http://') || sharePath.startsWith('https://')) {
    return sharePath;
  }
  const backendBase = BACKEND_BASE_URL.toString() || window.location.origin;
  return `${backendBase}${sharePath}`;
}

export async function fetchArtifactShares(): Promise<ArtifactShareRecord[]> {
  const response = await fetch(getApiUrl('/files/artifacts/shares'));
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? 'Failed to load share links');
  }
  return (await response.json()) as ArtifactShareRecord[];
}

export async function revokeArtifactShare(recordId: string): Promise<void> {
  const response = await fetch(getApiUrl(`/files/artifacts/shares/${recordId}`), {
    method: 'DELETE',
  });
  if (!response.ok && response.status !== 404) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? 'Failed to revoke share link');
  }
}

export function formatShareTimestamp(timestamp: number, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(timestamp * 1000));
}
