/**
 * [INPUT]
 * @/services/org-model-policy::fetchOrgModelPolicy, isModelAllowedByPolicy
 *
 * [OUTPUT]
 * - useOrgModelPolicyStore: Zustand store for org-level model policy
 *
 * [POS]
 * Caches org model policy locally. Provides `isModelAllowed(modelName)` for UI filtering.
 * Fail-open: if fetch fails or no policy set, all models are allowed.
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

export const useOrgModelPolicyStore = create<OrgModelPolicyState>((set, get) => ({
  patterns: [],
  restricted: false,
  initialized: false,
  loadPolicy: async () => {
    try {
      const data = await fetchOrgModelPolicy();
      set({ patterns: data.allowed_patterns, restricted: data.restricted, initialized: true });
    } catch {
      set({ patterns: [], restricted: false, initialized: true });
    }
  },
  isModelAllowed: (modelName: string) => {
    const { patterns } = get();
    return isModelAllowedByPolicy(modelName, patterns);
  },
}));
