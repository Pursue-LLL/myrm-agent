'use client';

/**
 * [INPUT]
 * - @/store/useOrgModelPolicyStore (POS: 组织模型白名单 Zustand 缓存)
 * - @/hooks/useOrgModelPolicySync (POS: visibility / Tauri focus refetch)
 *
 * [OUTPUT]
 * - useOrgModelPolicy: org model whitelist state + isModelAllowed filter
 *
 * [POS]
 * Settings 等页面的 org model policy hook。`isModelAllowed` 委托 store SSOT（含 fail-closed 哨兵）。
 */

import { useEffect } from 'react';
import { useOrgModelPolicySync } from '@/hooks/useOrgModelPolicySync';
import { useOrgModelPolicyStore } from '@/store/useOrgModelPolicyStore';

interface OrgModelPolicyState {
  patterns: string[];
  restricted: boolean;
  loading: boolean;
  isModelAllowed: (modelName: string) => boolean;
}

export function useOrgModelPolicy(): OrgModelPolicyState {
  useOrgModelPolicySync();

  const patterns = useOrgModelPolicyStore((state) => state.patterns);
  const restricted = useOrgModelPolicyStore((state) => state.restricted);
  const initialized = useOrgModelPolicyStore((state) => state.initialized);
  const loadPolicy = useOrgModelPolicyStore((state) => state.loadPolicy);
  const isModelAllowed = useOrgModelPolicyStore((state) => state.isModelAllowed);

  useEffect(() => {
    void loadPolicy();
  }, [loadPolicy]);

  return {
    patterns,
    restricted,
    loading: !initialized,
    isModelAllowed,
  };
}
