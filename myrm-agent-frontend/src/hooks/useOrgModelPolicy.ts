'use client';

/**
 * Hook for org-level model policy enforcement on frontend.
 *
 * Fetches org model whitelist once on mount, provides a filter function
 * to check if a model is allowed. No-op when no policy exists (unrestricted).
 */

import { useCallback, useEffect, useState } from 'react';
import { fetchOrgModelPolicy, isModelAllowedByPolicy } from '@/services/org-model-policy';

interface OrgModelPolicyState {
  patterns: string[];
  restricted: boolean;
  loading: boolean;
  isModelAllowed: (modelName: string) => boolean;
}

export function useOrgModelPolicy(): OrgModelPolicyState {
  const [patterns, setPatterns] = useState<string[]>([]);
  const [restricted, setRestricted] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchOrgModelPolicy()
      .then((data) => {
        if (cancelled) return;
        setPatterns(data.allowed_patterns);
        setRestricted(data.restricted);
      })
      .catch(() => {
        // Fail open: if fetch fails, don't restrict
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const isModelAllowed = useCallback(
    (modelName: string) => isModelAllowedByPolicy(modelName, patterns),
    [patterns],
  );

  return { patterns, restricted, loading, isModelAllowed };
}
