/**
 * [INPUT]
 * @/services/provider (POS: ProviderBalanceGauge, fetchProviderBalanceGauges)
 * zustand (POS: state management)
 *
 * [OUTPUT]
 * useProviderBalanceStore: global cache and polling store for LLM provider balances and quota health
 *
 * [POS]
 * Store layer tracking real-time provider balance observations, warnings, and manual re-probe triggers.
 */

import { create } from 'zustand';
import { fetchProviderBalanceGauges, type ProviderBalanceGauge } from '@/services/provider';

interface ProviderBalanceState {
  gauges: Record<string, ProviderBalanceGauge>; // provider_id -> gauge
  isLoading: boolean;
  lastFetchedAt: number | null;
  error: string | null;

  fetchGauges: (forceRefresh?: boolean) => Promise<void>;
  getGauge: (providerId: string | null | undefined) => ProviderBalanceGauge | undefined;
}

export const useProviderBalanceStore = create<ProviderBalanceState>((set, get) => ({
  gauges: {},
  isLoading: false,
  lastFetchedAt: null,
  error: null,

  fetchGauges: async (forceRefresh = false) => {
    // If not forced and fetched within 60s, skip
    const state = get();
    const now = Date.now();
    if (!forceRefresh && state.lastFetchedAt && now - state.lastFetchedAt < 60_000) {
      return;
    }

    set({ isLoading: true, error: null });
    try {
      const list = await fetchProviderBalanceGauges(forceRefresh);
      const map: Record<string, ProviderBalanceGauge> = {};
      for (const item of list) {
        if (item.provider_id) {
          map[item.provider_id.toLowerCase()] = item;
        }
      }
      set({ gauges: map, isLoading: false, lastFetchedAt: Date.now() });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      set({ isLoading: false, error: msg });
    }
  },

  getGauge: (providerId: string | null | undefined) => {
    if (!providerId) return undefined;
    return get().gauges[providerId.toLowerCase()];
  },
}));

export default useProviderBalanceStore;
