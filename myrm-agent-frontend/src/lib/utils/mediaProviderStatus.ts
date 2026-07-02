import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';
import type { VideoGenerationProvider } from '@/services/config/types';

export interface MediaProviderStatus {
  name: string;
  hasApiKey: boolean;
  healthy: boolean;
  configured: boolean;
  defaultModel?: string;
  models?: Array<{ id: string; name: string }>;
}

export const VIDEO_PROVIDER_CONFIG_IDS: Record<VideoGenerationProvider, string> = {
  openai: 'openai',
  gemini: 'gemini',
  qwen: 'dashscope',
  minimax: 'minimax',
};

export async function fetchMediaProviderStatus(): Promise<Record<string, MediaProviderStatus>> {
  try {
    const resp = await fetch(`${getBackendUrl()}/api/v1/agents/media-provider-status`, {
      headers: getAuthHeaders(),
    });
    const data = await resp.json();
    if (data.success && data.data?.providers) {
      return data.data.providers as Record<string, MediaProviderStatus>;
    }
  } catch {
    /* network error — fall back to empty */
  }
  return {};
}

/** Map image model id to provider storage id (aligned with server `_resolve_image_api_key_provider`). */
export function resolveImageProviderId(model: string): string {
  const normalized = model.toLowerCase();
  if (normalized.startsWith('gemini/') || normalized.includes('imagen')) {
    return 'gemini';
  }
  if (normalized.startsWith('flux/')) {
    return 'together_ai';
  }
  if (normalized.startsWith('stability/')) {
    return 'stability';
  }
  return 'openai';
}
