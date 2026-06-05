import { apiRequest } from '@/lib/api';

export interface ReadinessResponse {
  provider: {
    is_ready: boolean;
    missing_items: string[];
    suggestions: string[];
  };
  search: {
    is_ready: boolean;
    missing_items?: string[];
    suggestions?: string[];
  };
  onboarding_completed: boolean;
}

export async function getReadinessStatus(): Promise<ReadinessResponse> {
  return apiRequest<ReadinessResponse>('/config/readiness', { method: 'GET' });
}

export async function completeOnboarding(): Promise<{ success: boolean; message: string }> {
  return apiRequest<{ success: boolean; message: string }>('/config/onboarding/complete', { method: 'POST' });
}
