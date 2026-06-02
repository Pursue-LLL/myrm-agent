import { getAuthHeaders } from '@/lib/utils/authHeaders';

export interface RateLimitBucket {
  limit: number;
  remaining: number;
  reset_seconds: number;
  updated_at: number;
  usage_pct: number;
  remaining_seconds_now: number;
}

export interface RateLimitState {
  provider: string;
  model: string;
  rpm: RateLimitBucket | null;
  rph: RateLimitBucket | null;
  tpm: RateLimitBucket | null;
  tph: RateLimitBucket | null;
  highest_usage_pct: number;
  updated_at: number;
}

export interface RateLimitsResponse {
  states: RateLimitState[];
}

export async function fetchRateLimits(): Promise<RateLimitsResponse> {
  const headers = getAuthHeaders();
  const response = await fetch('/api/statistics/rate-limits', {
    headers,
  });

  if (!response.ok) {
    throw new Error('Failed to fetch rate limits');
  }

  return response.json();
}
