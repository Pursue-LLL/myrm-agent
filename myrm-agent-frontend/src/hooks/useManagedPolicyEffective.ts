/**
 * [INPUT]
 * - @/lib/managedPolicyMatch::ManagedPolicyEffective (POS: Org MAP fnmatch 与约束 helpers)
 * - @/lib/deploy-mode::isTauriRuntime (POS: 部署模式探测)
 * - @/services/config::getConfigSyncManager (POS: 前端安全配置同步)
 * - GET /api/v1/security/managed-policy/effective (POS: 进程级 MAP 只读 API)
 *
 * [OUTPUT]
 * - useManagedPolicyEffective: org MAP 有效策略 React 状态（mount + SSE push + tab visible / Tauri focus refetch）
 *
 * [POS]
 * Org MAP 前端 SSOT hook。读取 server effective MAP，并在 org disableYolo 时清除 stale 本地 YOLO。
 */

import { useEffect, useState } from 'react';
import { isTauriRuntime } from '@/lib/deploy-mode';
import {
  type ManagedPolicyEffective,
} from '@/lib/managedPolicyMatch';
import {
  MANAGED_POLICY_UPDATED_EVENT,
  type ManagedPolicyUpdatedDetail,
} from '@/lib/managedPolicyEffectiveEvents';
import { getConfigSyncManager } from '@/services/config';

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

type ManagedPolicyEffectivePayload = ManagedPolicyEffective & {
  active?: boolean;
  revision?: number;
};

let inflightFetch: Promise<ManagedPolicyEffectivePayload | null> | null = null;
let lastAppliedRevision = -1;

function clearStaleYoloWhenOrgDisabled(disableYolo: boolean): void {
  if (!disableYolo) {
    return;
  }
  const syncManager = getConfigSyncManager();
  const config = syncManager.get('securityConfig');
  if (!config?.yoloModeEnabled) {
    return;
  }
  syncManager.set('securityConfig', {
    ...config,
    yoloModeEnabled: false,
    yoloModeTimeout: undefined,
    yoloModeEnabledAt: undefined,
  });
}

function toManagedPolicyState(data: ManagedPolicyEffectivePayload): ManagedPolicyEffectiveState {
  const disableYolo = Boolean(data.disableYolo);
  return {
    active: Boolean(data.active),
    policy: {
      active: Boolean(data.active),
      disableYolo,
      disableAllowAlways: Boolean(data.disableAllowAlways),
      forceAutoReviewForModels: data.forceAutoReviewForModels ?? [],
      ignoreAllowlistForModels: data.ignoreAllowlistForModels ?? [],
    },
    loaded: true,
  };
}

async function fetchManagedPolicyEffectivePayload(): Promise<ManagedPolicyEffectivePayload | null> {
  if (inflightFetch) {
    return inflightFetch;
  }

  inflightFetch = (async () => {
    try {
      const response = await fetch('/api/v1/security/managed-policy/effective');
      if (!response.ok) {
        return null;
      }
      return (await response.json()) as ManagedPolicyEffectivePayload;
    } catch {
      return null;
    } finally {
      inflightFetch = null;
    }
  })();

  return inflightFetch;
}

export function useManagedPolicyEffective(): ManagedPolicyEffectiveState {
  const [state, setState] = useState<ManagedPolicyEffectiveState>(EMPTY);

  useEffect(() => {
    let cancelled = false;
    let requestId = 0;

    const load = async () => {
      const currentId = ++requestId;
      const data = await fetchManagedPolicyEffectivePayload();
      if (cancelled || currentId !== requestId) {
        return;
      }
      if (!data) {
        setState((prev) => (prev.loaded ? prev : { ...prev, loaded: true }));
        return;
      }
      const disableYolo = Boolean(data.disableYolo);
      if (Boolean(data.active) && disableYolo) {
        clearStaleYoloWhenOrgDisabled(true);
      }
      if (typeof data.revision === 'number') {
        lastAppliedRevision = data.revision;
      }
      setState(toManagedPolicyState(data));
    };

    const refetchWhenVisible = () => {
      if (document.visibilityState === 'visible') {
        void load();
      }
    };

    const refetchOnManagedPolicyUpdated = (event: Event) => {
      const detail = (event as CustomEvent<ManagedPolicyUpdatedDetail>).detail;
      if (
        typeof detail?.revision === 'number'
        && detail.revision <= lastAppliedRevision
      ) {
        return;
      }
      void load();
    };

    void load();
    document.addEventListener('visibilitychange', refetchWhenVisible);
    window.addEventListener(MANAGED_POLICY_UPDATED_EVENT, refetchOnManagedPolicyUpdated);

    let unlistenFocus: (() => void) | undefined;
    if (isTauriRuntime()) {
      void import('@tauri-apps/api/window')
        .then(({ getCurrentWindow }) =>
          getCurrentWindow().onFocusChanged(({ payload: focused }) => {
            if (focused && document.visibilityState === 'visible') {
              void load();
            }
          }),
        )
        .then((unlisten) => {
          if (!cancelled) {
            unlistenFocus = unlisten;
          } else {
            unlisten();
          }
        })
        .catch(() => undefined);
    }

    return () => {
      cancelled = true;
      document.removeEventListener('visibilitychange', refetchWhenVisible);
      window.removeEventListener(MANAGED_POLICY_UPDATED_EVENT, refetchOnManagedPolicyUpdated);
      unlistenFocus?.();
    };
  }, []);

  return state;
}
