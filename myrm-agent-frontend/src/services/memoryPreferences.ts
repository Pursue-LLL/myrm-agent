/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Preference stability DTOs and request helpers.
 *
 * [POS]
 * Frontend preference stability API client. Owns preference facet listing and user pin/forget operations.
 */

import { apiRequest } from '@/lib/api';

export type PreferenceLifecycleType = 'active' | 'provisional' | 'candidate' | 'dropped';

export interface PreferenceFacet {
  id: string;
  key: string;
  value: string;
  category: string;
  cue: string;
  lifecycle: PreferenceLifecycleType;
  stability: number;
  evidence_count: number;
  memory_ids: string[];
  first_seen: string;
  last_seen: string;
  user_pinned: boolean;
  user_forgotten: boolean;
}

export interface PreferenceFacetListResponse {
  items: PreferenceFacet[];
  total: number;
  active_count: number;
  provisional_count: number;
  candidate_count: number;
}

export const getPreferences = async (lifecycle?: PreferenceLifecycleType): Promise<PreferenceFacetListResponse> => {
  const qs = lifecycle ? `?lifecycle=${lifecycle}` : '';
  return apiRequest<PreferenceFacetListResponse>(`/memory/preferences${qs}`);
};

export const pinPreference = async (facetId: string): Promise<{ success: boolean }> => {
  return apiRequest<{ success: boolean }>(`/memory/preferences/${facetId}/pin`, {
    method: 'POST',
  });
};

export const forgetPreference = async (facetId: string): Promise<{ success: boolean }> => {
  return apiRequest<{ success: boolean }>(`/memory/preferences/${facetId}/forget`, {
    method: 'POST',
  });
};

export const unpinPreference = async (facetId: string): Promise<{ success: boolean }> => {
  return apiRequest<{ success: boolean }>(`/memory/preferences/${facetId}/unpin`, {
    method: 'POST',
  });
};

export const unforgetPreference = async (facetId: string): Promise<{ success: boolean }> => {
  return apiRequest<{ success: boolean }>(`/memory/preferences/${facetId}/unforget`, {
    method: 'POST',
  });
};
