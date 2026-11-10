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

/** The server's radar state for one session: the five weights sit directly on the object. */
export interface PreferenceRadarStateResponse extends RadarDimensionValues {
  session_id: string;
  locked: boolean;
  last_updated: string;
  effective_signal_weights: Record<string, number>;
}

/** Weights to set, the lock flag, and `reset_to_neutral` to put every weight back to 1.0. */
export type PreferenceRadarTuneRequest = Partial<RadarDimensionValues> & {
  locked?: boolean;
  reset_to_neutral?: boolean;
};

/** A background read: a failure must not raise an error notice of its own. */
export const getPreferenceRadarState = async (sessionId: string): Promise<PreferenceRadarStateResponse> => {
  return apiRequest<PreferenceRadarStateResponse>(`/memory/radar/${encodeURIComponent(sessionId)}`, { silent: true });
};

export const tunePreferenceRadar = async (
  sessionId: string,
  req: PreferenceRadarTuneRequest,
): Promise<PreferenceRadarStateResponse> => {
  return apiRequest<PreferenceRadarStateResponse>(`/memory/radar/${encodeURIComponent(sessionId)}/tune`, {
    method: 'POST',
    body: JSON.stringify(req),
  });
};
