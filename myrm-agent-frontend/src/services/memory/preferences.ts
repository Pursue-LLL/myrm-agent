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

export interface RadarDimensionValues {
  recency: number;
  actionability: number;
  technical_depth: number;
  conciseness: number;
  breadth: number;
}

export interface PreferenceRadarStateResponse {
  session_id: string;
  dimensions: RadarDimensionValues;
  effective_signal_weights: Record<string, number>;
  locked: boolean;
  updated_at: string;
}

export const getPreferenceRadarState = async (sessionId: string): Promise<PreferenceRadarStateResponse> => {
  return apiRequest<PreferenceRadarStateResponse>(`/memory/radar/${encodeURIComponent(sessionId)}`);
};

export const tunePreferenceRadar = async (
  sessionId: string,
  req: {
    dimensions?: Partial<RadarDimensionValues>;
    locked?: boolean;
    reset_to_baseline?: boolean;
  }
): Promise<PreferenceRadarStateResponse> => {
  return apiRequest<PreferenceRadarStateResponse>(`/memory/radar/${encodeURIComponent(sessionId)}/tune`, {
    method: 'POST',
    body: JSON.stringify(req),
  });
};

