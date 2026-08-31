/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: 前端 API 接入层)
 *
 * [OUTPUT]
 * - OAuthCredentialItem, listOAuthCredentials
 *
 * [POS]
 * 个人 SaaS OAuth 集成凭证只读 API 客户端，供 Settings 披露与集成管理复用。
 */

import { apiRequest } from '@/lib/api';

export interface OAuthCredentialItem {
  issuer: string;
  user_id: string | null;
  scope: string | null;
  expires_at: number | null;
  connected: boolean;
}

export async function listOAuthCredentials(): Promise<OAuthCredentialItem[]> {
  return apiRequest<OAuthCredentialItem[]>('/integrations/oauth', { silent: true });
}
