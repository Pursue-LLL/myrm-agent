'use client';

import useSWR from 'swr';
import useAuthStore from '@/store/useAuthStore';
import { isLocalMode } from '@/lib/deploy-mode';
import { fetchEntitlements, type EntitlementSnapshot } from '@/lib/cp-billing';

export function useEntitlements() {
  const { isAuthenticated, token } = useAuthStore();
  const local = isLocalMode();

  const { data, error, isLoading, mutate } = useSWR<EntitlementSnapshot>(
    isAuthenticated && !local && token ? ['cp-entitlements', token] : null,
    () => fetchEntitlements(token!),
    {
      revalidateOnFocus: true,
      dedupingInterval: 30000,
      suspense: false,
    },
  );

  return {
    entitlements: data,
    isLoading,
    error,
    refresh: mutate,
  };
}
