import { getApiUrl } from '@/lib/api';

export type HostingProviderType = 'vercel' | 'cloudflare_pages' | 'netlify' | 'http_webhook';

export interface HostingTarget {
  id: string;
  name: string;
  provider_type: HostingProviderType;
  config: Record<string, string>;
  is_default: boolean;
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

export async function testHostingTarget(targetId: string): Promise<{ ok: boolean; message: string }> {
  const response = await fetch(getApiUrl(`/api/v1/files/artifacts/hosting/targets/${targetId}/test`), {
    method: 'POST',
  });
  if (!response.ok) {
    return { ok: false, message: 'Test request failed' };
  }
  return (await response.json()) as { ok: boolean; message: string };
}
