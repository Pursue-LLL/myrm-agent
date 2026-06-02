import { apiRequest } from '@/lib/api';

export type TunnelStatus = {
  running: boolean;
  url: string | null;
  target_port: number | null;
  ingress_synced: boolean;
};

export const systemService = {
  /**
   * Get the computed public ingress base URL.
   */
  async getIngressUrl(): Promise<string> {
    const data = await apiRequest<{ ingress_url: string }>(`/system/ingress-url?t=${Date.now()}`);
    return data.ingress_url;
  },

  async getTunnelStatus(): Promise<TunnelStatus> {
    return apiRequest<TunnelStatus>('/system/tunnel/status');
  },

  async startTunnel(port: number, passwordProtectionEnabled: boolean): Promise<TunnelStatus> {
    return apiRequest<TunnelStatus>('/system/tunnel/start', {
      method: 'POST',
      body: JSON.stringify({
        port,
        password_protection_enabled: passwordProtectionEnabled,
      }),
    });
  },

  async stopTunnel(): Promise<TunnelStatus> {
    return apiRequest<TunnelStatus>('/system/tunnel/stop', {
      method: 'POST',
    });
  },

  async getLocalNetwork(port: number): Promise<{ ip: string; url: string; hint: string }> {
    return apiRequest<{ ip: string; url: string; hint: string }>(
      `/system/local-network?port=${port}`,
    );
  },

  async testIngressHealth(baseUrl: string): Promise<boolean> {
    const normalized = baseUrl.replace(/\/+$/, '');
    const response = await fetch(`${normalized}/api/v1/health`, { method: 'GET' });
    return response.ok;
  },
};
