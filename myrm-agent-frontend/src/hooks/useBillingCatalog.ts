'use client';

import useSWR from 'swr';
import { fetchBillingCatalog, type BillingCatalogResponse } from '@/lib/cp-billing';
import { isLocalMode } from '@/lib/deploy-mode';

export function useBillingCatalog() {
  const local = isLocalMode();

  const { data, error, isLoading } = useSWR<BillingCatalogResponse>(
    local ? null : ['cp-billing-catalog'],
    () => fetchBillingCatalog(),
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
    },
  );

  return {
    catalog: data,
    isLoading,
    error,
  };
}
