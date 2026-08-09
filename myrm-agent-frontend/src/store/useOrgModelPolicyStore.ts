/**
 * [INPUT]
 * @/services/org-model-policy::fetchOrgModelPolicy, isModelAllowedByPolicy
 *
 * [OUTPUT]
 * - useOrgModelPolicyStore: Zustand store for org-level model policy
 *
 * [POS]
 * Caches org model policy locally. Provides `isModelAllowed(modelName)` for UI filtering.
 * Fail-closed UI in sandbox: if fetch fails, grey out all models until policy loads.
 * `loadPolicy()` is idempotent and dedupes concurrent fetches.
 */

import { create } from 'zustand';
import { fetchOrgModelPolicy, isModelAllowedByPolicy } from '@/services/org-model-policy';

interface OrgModelPolicyState {
  patterns: string[];
  restricted: boolean;
  initialized: boolean;
  loadPolicy: () => Promise<void>;
  isModelAllowed: (modelName: string) => boolean;
}

let inflightLoad: Promise<void> | null = null;

export const useOrgModelPolicyStore = create<OrgModelPolicyState>((set, get) => ({
  patterns: [],
  restricted: false,
  initialized: false,
  loadPolicy: async () => {
    if (inflightLoad) {
      return inflightLoad;
    }

    inflightLoad = (async () => {
      try {
        const data = await fetchOrgModelPolicy();
        set({ patterns: data.allowed_patterns, restricted: data.restricted, initialized: true });
      } catch {
        const failClosed = (await import('@/lib/deploy-mode')).isSandbox();
        set({ patterns: [], restricted: failClosed, initialized: true });
      } finally {
        inflightLoad = null;
      }
    })();

    return inflightLoad;
  },
  isModelAllowed: (modelName: string) => {
    const { patterns, restricted } = get();
    // Fail-closed sentinel: restricted with no patterns loaded yet → deny all.
    if (restricted && patterns.length === 0) {
      return false;
    }
    return isModelAllowedByPolicy(modelName, patterns);
  },
}));
