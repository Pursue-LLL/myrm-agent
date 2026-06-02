/**
 * BYOK Usage Analytics Hook
 *
 * Provides real-time global usage statistics for the user.
 */

import useSWR from 'swr';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8080/api/v1';

export interface UsageRadarData {
  total_calls: number;
  total_tokens: number;
  total_usd: number;
}

async function fetchUsageData(url: string): Promise<UsageRadarData> {
  const token = localStorage.getItem('auth_token');
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(url, { headers });
  if (!response.ok) {
    throw new Error('Failed to fetch usage radar');
  }

  const result = await response.json();
  return result.data;
}

export function useUsageAnalytics() {
  const { data, error, isLoading, mutate } = useSWR<UsageRadarData>(
    // Note: We can fetch even in local mode if the backend supports it,
    // but the original code guarded backend stats behind auth/SaaS checks.
    // If the local backend also tracks SQLite chats, we can allow it.
    // Assuming local mode API also provides /api/v1/analytics/usage/radar
    `${API_BASE_URL}/analytics/usage/radar`,
    fetchUsageData,
    {
      revalidateOnFocus: true,
      dedupingInterval: 10000,
      refreshInterval: 60000, // Poll every minute for active sessions
      suspense: false,
    },
  );

  return {
    usage: data || { total_calls: 0, total_tokens: 0, total_usd: 0 },
    isLoading,
    error,
    refresh: mutate,
  };
}
