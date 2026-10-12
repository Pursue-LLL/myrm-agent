/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Profile & Working Notes dual-layer DTOs and API request functions:
 * - checkProfileNotesIntake
 * - getProfileNotesWatermarks
 * - getProfileNotesContents
 * - updateProfileNotesContents
 *
 * [POS]
 * Frontend API client for Dual-Layer Profile & Working Notes Memory Budget Guard.
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export type WatermarkLevel = 'safe' | 'warning' | 'critical' | 'overflow';

export interface LayerWatermarkResponse {
  layer: string;
  current_chars: number;
  max_chars: number;
  usage_ratio: number;
  level: WatermarkLevel;
  warning_message: string | null;
}

export interface ProfileNotesStatusResponse {
  user_watermark: LayerWatermarkResponse;
  memory_watermark: LayerWatermarkResponse;
}

export interface ProfileNotesIntakeRequest {
  content: string;
  layer_hint?: string | null;
}

export interface ProfileNotesIntakeResponse {
  accepted: boolean;
  target_layer: string | null;
  rejected_reason: string | null;
  garbage_category: string | null;
}

export interface ProfileNotesUpdateRequest {
  user_content?: string | null;
  memory_content?: string | null;
}

export interface ProfileNotesContentResponse {
  user_content: string;
  memory_content: string;
  user_watermark: LayerWatermarkResponse;
  memory_watermark: LayerWatermarkResponse;
}

export const checkProfileNotesIntake = async (
  request: ProfileNotesIntakeRequest,
): Promise<ProfileNotesIntakeResponse> => {
  return apiRequest<ProfileNotesIntakeResponse>('/memory/profile-notes/intake-check', {
    method: 'POST',
    body: JSON.stringify(request),
    headers: {
      'Content-Type': 'application/json',
    },
  });
};

export const getProfileNotesWatermarks = async (): Promise<ProfileNotesStatusResponse> => {
  return apiRequest<ProfileNotesStatusResponse>('/memory/profile-notes/watermarks');
};

export const getProfileNotesContents = async (): Promise<ProfileNotesContentResponse> => {
  return apiRequest<ProfileNotesContentResponse>('/memory/profile-notes/contents');
};

export const updateProfileNotesContents = async (
  request: ProfileNotesUpdateRequest,
): Promise<ProfileNotesContentResponse> => {
  return apiRequest<ProfileNotesContentResponse>('/memory/profile-notes/contents', {
    method: 'PUT',
    body: JSON.stringify(request),
    headers: {
      'Content-Type': 'application/json',
    },
  });
};
