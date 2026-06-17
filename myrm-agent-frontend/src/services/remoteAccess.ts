import { apiRequest } from '@/lib/api';
import type { ActiveSessionsResponse } from '@/services/agent';

export type TunnelStatus = {
  state: 'stopped' | 'starting' | 'running' | 'error';
  publicUrl: string;
  error: string;
  provider: string;
};

export type PairingTokenResponse = {
  token: string;
  mobilePath: string;
};

export const remoteAccessService = {
  async getTunnelStatus(): Promise<TunnelStatus> {
    return apiRequest<TunnelStatus>('/remote-access/tunnel/status');
  },

  async startTunnel(localPort?: number): Promise<TunnelStatus> {
    return apiRequest<TunnelStatus>('/remote-access/tunnel/start', {
      method: 'POST',
      body: JSON.stringify({ local_port: localPort ?? null }),
    });
  },

  async stopTunnel(): Promise<TunnelStatus> {
    return apiRequest<TunnelStatus>('/remote-access/tunnel/stop', { method: 'POST' });
  },

  async createPairingToken(chatId?: string): Promise<PairingTokenResponse> {
    return apiRequest<PairingTokenResponse>('/remote-access/pairing-token', {
      method: 'POST',
      body: JSON.stringify({ chat_id: chatId ?? null, purpose: 'mobile_hub' }),
    });
  },

  async getMobileSessions(pairToken?: string): Promise<ActiveSessionsResponse> {
    const query = pairToken ? `?pair=${encodeURIComponent(pairToken)}` : '';
    return apiRequest<ActiveSessionsResponse>(`/remote-access/mobile/sessions${query}`);
  },
};
