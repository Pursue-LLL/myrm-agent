export type BackendDevMode = 'split_dev' | 'standalone_webui';

export interface BackendHealthPayload {
  status: string;
  dev_mode?: BackendDevMode;
  listen_port?: number;
  listen_host?: string;
  frontend_proxy_port?: number;
}

export async function fetchBackendHealth(): Promise<BackendHealthPayload | null> {
  try {
    const response = await fetch('/api/v1/health', { cache: 'no-store' });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as BackendHealthPayload;
  } catch {
    return null;
  }
}
