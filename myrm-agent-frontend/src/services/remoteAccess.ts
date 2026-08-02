import { apiRequest } from '@/lib/api';
import { isMobileRemoteSurface, mobileApiRequest, mobileRemotePost } from '@/lib/mobileRemote';
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
  mobileUrl?: string;
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

  async createPairingToken(
    chatId?: string,
    purpose?: 'mobile_hub' | 'mobile_hub_list' | 'browser_takeover',
  ): Promise<PairingTokenResponse> {
    const resolvedPurpose = purpose ?? (chatId ? 'mobile_hub' : 'mobile_hub_list');
    const body = { chat_id: chatId ?? null, purpose: resolvedPurpose };
    if (isMobileRemoteSurface()) {
      return mobileRemotePost<PairingTokenResponse>('/api/v1/remote-access/pairing-token', body);
    }
    return apiRequest<PairingTokenResponse>('/remote-access/pairing-token', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  async refreshPairingToken(): Promise<PairingTokenResponse> {
    if (isMobileRemoteSurface()) {
      return mobileApiRequest<PairingTokenResponse>('/api/v1/remote-access/pairing-token/refresh', {
        method: 'POST',
      });
    }
    return apiRequest<PairingTokenResponse>('/remote-access/pairing-token/refresh', {
      method: 'POST',
    });
  },

  async getMobileSessions(_pairToken?: string): Promise<ActiveSessionsResponse> {
    if (isMobileRemoteSurface()) {
      return mobileApiRequest<ActiveSessionsResponse>('/api/v1/remote-access/mobile/sessions');
    }
    const query = _pairToken ? `?pair=${encodeURIComponent(_pairToken)}` : '';
    return apiRequest<ActiveSessionsResponse>(`/remote-access/mobile/sessions${query}`);
  },

  async getSpawnOptions(): Promise<SpawnOptionsResponse> {
    if (isMobileRemoteSurface()) {
      return mobileApiRequest<SpawnOptionsResponse>('/api/v1/remote-access/mobile/spawn-options');
    }
    return apiRequest<SpawnOptionsResponse>('/remote-access/mobile/spawn-options');
  },

  async spawnMobileSession(params: SpawnMobileSessionParams): Promise<SpawnMobileSessionResponse> {
    const body = {
      agent_id: params.agentId,
      project_id: params.projectId ?? null,
      initial_message: params.initialMessage,
    };
    if (isMobileRemoteSurface()) {
      return mobileRemotePost<SpawnMobileSessionResponse>('/api/v1/remote-access/mobile/spawn', body);
    }
    return apiRequest<SpawnMobileSessionResponse>('/remote-access/mobile/spawn', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  async getE2EEPublicKey(): Promise<{ publicKeyB64: string }> {
    return apiRequest<{ publicKeyB64: string }>('/remote-access/e2ee/public-key');
  },
};

export type SpawnOptionAgent = { id: string; name: string; avatar: string | null };
export type SpawnOptionProject = { id: string; name: string; color: string | null };

export type SpawnOptionsResponse = {
  agents: SpawnOptionAgent[];
  projects: SpawnOptionProject[];
  defaultAgentId: string | null;
};

export type SpawnMobileSessionParams = {
  agentId: string;
  projectId?: string;
  initialMessage: string;
};

export type SpawnMobileSessionResponse = {
  chatId: string;
  token: string;
  mobilePath: string;
  mobileUrl?: string;
};
