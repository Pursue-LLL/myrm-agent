/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * getSharedContextMemoryHealth: Shared Context memory dependency health API client.
 *
 * [POS]
 * Frontend Shared Context health API client. Keeps health preflight isolated from the large memory service module.
 */

import { apiRequest } from '@/lib/api';

export type SharedContextMemoryHealthStatus = 'ready' | 'not_configured' | 'unreachable';

export interface SharedContextMemoryHealthResponse {
  ready: boolean;
  status: SharedContextMemoryHealthStatus;
  model: string;
  api_base_configured: boolean;
  api_key_configured: boolean;
  probed: boolean;
  reason?: string | null;
  retryable: boolean;
  checked_at: string;
  vector_dimension?: number | null;
}

export const getSharedContextMemoryHealth = async (probe = false): Promise<SharedContextMemoryHealthResponse> => {
  return apiRequest<SharedContextMemoryHealthResponse>(`/memory/shared-contexts/health/memory?probe=${probe}`);
};
