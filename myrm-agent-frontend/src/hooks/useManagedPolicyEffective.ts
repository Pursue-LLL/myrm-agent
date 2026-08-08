import { useEffect, useState } from 'react';
import {
  type ManagedPolicyEffective,
} from '@/lib/managedPolicyMatch';

interface ManagedPolicyEffectiveState {
  policy: ManagedPolicyEffective;
  active: boolean;
  loaded: boolean;
}

const EMPTY: ManagedPolicyEffectiveState = {
  policy: {},
  active: false,
  loaded: false,
};

export function useManagedPolicyEffective(): ManagedPolicyEffectiveState {
  const [state, setState] = useState<ManagedPolicyEffectiveState>(EMPTY);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const response = await fetch('/api/v1/security/managed-policy/effective');
        if (!response.ok) {
          return;
        }
        const data = (await response.json()) as ManagedPolicyEffective & { active?: boolean };
        if (cancelled) {
          return;
        }
        setState({
          active: Boolean(data.active),
          policy: {
            active: Boolean(data.active),
            disableYolo: Boolean(data.disableYolo),
            disableAllowAlways: Boolean(data.disableAllowAlways),
            forceAutoReviewForModels: data.forceAutoReviewForModels ?? [],
            ignoreAllowlistForModels: data.ignoreAllowlistForModels ?? [],
          },
          loaded: true,
        });
      } catch {
        /* local/Tauri: endpoint empty or unreachable */
      } finally {
        if (!cancelled) {
          setState((prev) => (prev.loaded ? prev : { ...prev, loaded: true }));
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
