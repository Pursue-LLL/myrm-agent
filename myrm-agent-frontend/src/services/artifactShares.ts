import { getApiUrl } from '@/lib/api';

export interface ArtifactShareRecord {
  id: string;
  artifact_id: string;
  artifact_name: string;
  artifact_type: string | null;
  password_protected: boolean;
  created_at: number;
  expires_at: number;
}

export async function fetchArtifactShares(): Promise<ArtifactShareRecord[]> {
  const response = await fetch(getApiUrl('/api/v1/files/artifacts/shares'));
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? 'Failed to load share links');
  }
  return (await response.json()) as ArtifactShareRecord[];
}

export async function revokeArtifactShare(recordId: string): Promise<void> {
  const response = await fetch(getApiUrl(`/api/v1/files/artifacts/shares/${recordId}`), {
    method: 'DELETE',
  });
  if (!response.ok && response.status !== 404) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? 'Failed to revoke share link');
  }
}

export function formatShareExpiry(expiresAt: number, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(expiresAt * 1000));
}
