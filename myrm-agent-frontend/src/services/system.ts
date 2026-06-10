import { apiRequest } from '@/lib/api';

export type IngressRequirementSnapshot = {
  required: boolean;
  has_public_ingress: boolean;
  reasons: string[];
  channels: Record<string, 'outbound' | 'inbound'>;
};

export const systemService = {
  /**
   * Get the computed public ingress base URL.
   */
  async getIngressRequirement(): Promise<IngressRequirementSnapshot> {
    return apiRequest<IngressRequirementSnapshot>(`/system/ingress-requirement?t=${Date.now()}`);
  },

  async getIngressUrl(): Promise<string> {
    const data = await apiRequest<{ ingress_url: string }>(`/system/ingress-url?t=${Date.now()}`);
    return data.ingress_url;
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
