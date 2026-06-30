import { getApiUrl } from '@/lib/api';

export type HostingProviderType = 'vercel' | 'cloudflare_pages' | 'netlify' | 'http_webhook';

export interface HostingTarget {
  id: string;
  name: string;
  provider_type: HostingProviderType;
  config: Record<string, string>;
  is_default: boolean;
}

export interface ArtifactPublication {
  id: string;
  hosting_target_id: string;
  hosting_target_name?: string | null;
  publication_url: string | null;
  publication_status: string | null;
  publication_project_ref: string | null;
  publication_version_id: string | null;
  updated_at: string | null;
}

export interface PublishPreflight {
  deployable: boolean;
  reason: string;
  message: string;
  hint: string | null;
}

export interface PublishResult {
  provider_publication_ref: string;
  url: string;
  status: string;
  publication_url: string;
  publication_status: string;
  publication_project_ref?: string | null;
  publication_version_id?: string | null;
  latest_version_id?: string | null;
  hosting_target_id: string;
  publication: ArtifactPublication | null;
}

export async function fetchHostingTargets(): Promise<HostingTarget[]> {
  const response = await fetch(getApiUrl('/api/v1/files/artifacts/hosting/targets'));
  if (!response.ok) {
    return [];
  }
  const data = (await response.json()) as { targets?: HostingTarget[] };
  return data.targets ?? [];
}

export async function saveHostingTarget(target: Omit<HostingTarget, 'id'> & { id?: string }): Promise<HostingTarget | null> {
  const method = target.id ? 'PUT' : 'POST';
  const url = target.id
    ? getApiUrl(`/api/v1/files/artifacts/hosting/targets/${target.id}`)
    : getApiUrl('/api/v1/files/artifacts/hosting/targets');
  const response = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(target),
  });
  if (!response.ok) {
    return null;
  }
  return (await response.json()) as HostingTarget;
}

export async function deleteHostingTarget(targetId: string): Promise<boolean> {
  const response = await fetch(getApiUrl(`/api/v1/files/artifacts/hosting/targets/${targetId}`), {
    method: 'DELETE',
  });
  return response.ok;
}

export async function saveTargetCredentials(targetId: string, credentials: Record<string, string>): Promise<boolean> {
  const response = await fetch(getApiUrl(`/api/v1/files/artifacts/hosting/targets/${targetId}/credentials`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credentials }),
  });
  return response.ok;
}

export async function fetchTargetCredentialStatus(
  targetId: string,
): Promise<{ configured: boolean; platform_available: boolean }> {
  const response = await fetch(getApiUrl(`/api/v1/files/artifacts/hosting/targets/${targetId}/credentials`));
  if (!response.ok) {
    return { configured: false, platform_available: false };
  }
  const data = (await response.json()) as { configured?: boolean; platform_available?: boolean };
  return {
    configured: Boolean(data.configured),
    platform_available: Boolean(data.platform_available),
  };
}

export async function testHostingTarget(targetId: string): Promise<{ ok: boolean; message: string }> {
  const response = await fetch(getApiUrl(`/api/v1/files/artifacts/hosting/targets/${targetId}/test`), {
    method: 'POST',
  });
  if (!response.ok) {
    return { ok: false, message: 'Test request failed' };
  }
  return (await response.json()) as { ok: boolean; message: string };
}

export async function makeDefaultHostingTarget(targetId: string): Promise<HostingTarget | null> {
  const response = await fetch(getApiUrl(`/api/v1/files/artifacts/hosting/targets/${targetId}/make-default`), {
    method: 'POST',
  });
  if (!response.ok) {
    return null;
  }
  return (await response.json()) as HostingTarget;
}

export async function fetchArtifactPublications(artifactId: string): Promise<ArtifactPublication[]> {
  const response = await fetch(getApiUrl(`/api/v1/files/artifacts/${artifactId}/publications`));
  if (!response.ok) {
    return [];
  }
  const data = (await response.json()) as { publications?: ArtifactPublication[] };
  return data.publications ?? [];
}

export async function fetchPublishPreflight(artifactId: string, targetId?: string): Promise<PublishPreflight | null> {
  const query = targetId ? `?target_id=${encodeURIComponent(targetId)}` : '';
  const response = await fetch(getApiUrl(`/api/v1/files/artifacts/${artifactId}/publish/preflight${query}`));
  if (!response.ok) {
    return null;
  }
  return (await response.json()) as PublishPreflight;
}

export async function publishArtifact(
  artifactId: string,
  targetId: string,
  token = '',
): Promise<PublishResult> {
  const response = await fetch(getApiUrl(`/api/v1/files/artifacts/${artifactId}/publish`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_id: targetId, token }),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? 'Publication failed');
  }
  return (await response.json()) as PublishResult;
}

export function buildPublishStatusWsUrl(
  artifactId: string,
  providerPublicationRef: string,
  targetId: string,
): string {
  const wsProtocol = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsHost = getApiUrl('').replace(/^https?:\/\//, '');
  return `${wsProtocol}//${wsHost}/api/v1/files/artifacts/${artifactId}/publish/status/${providerPublicationRef}?target_id=${encodeURIComponent(targetId)}`;
}

export const PROVIDER_LABELS: Record<HostingProviderType, string> = {
  vercel: 'Vercel',
  cloudflare_pages: 'Cloudflare Pages',
  netlify: 'Netlify',
  http_webhook: 'HTTP Webhook',
};
