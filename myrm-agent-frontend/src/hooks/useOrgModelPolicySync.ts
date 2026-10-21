/**
 * [INPUT]
 * - @/store/useOrgModelPolicyStore::useOrgModelPolicyStore (POS: 组织模型白名单 Zustand 缓存)
 * - @/lib/deploy-mode::isTauriRuntime (POS: 部署模式探测)
 *
 * [OUTPUT]
 * - useOrgModelPolicySync: tab visible / Tauri focus 时 refetch org model policy
 *
 * [POS]
 * 云 Enterprise 成员侧 org model policy 刷新 hook。Admin fanout 更新沙箱 DB 后，
 * 在 picker 打开或页面重新可见时拉取最新 whitelist（无 SSE；model policy 仅影响 UI 灰显）。
 */

'use client';

import { useEffect } from 'react';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { useOrgModelPolicyStore } from '@/store/useOrgModelPolicyStore';

let syncRefCount = 0;
let removeVisibilityListener: (() => void) | undefined;
let removeTauriFocusListener: (() => void) | undefined;

function refetchOrgModelPolicy(): void {
  void useOrgModelPolicyStore.getState().loadPolicy();
}

function attachOrgModelPolicySyncListeners(): void {
  if (removeVisibilityListener) {
    return;
  }

  const onVisibilityChange = () => {
    if (document.visibilityState === 'visible') {
      refetchOrgModelPolicy();
    }
  };

  document.addEventListener('visibilitychange', onVisibilityChange);
  removeVisibilityListener = () => {
    document.removeEventListener('visibilitychange', onVisibilityChange);
  };

  if (isTauriRuntime()) {
    void import('@tauri-apps/api/window')
      .then(({ getCurrentWindow }) =>
        getCurrentWindow().onFocusChanged(({ payload: focused }) => {
          if (focused && document.visibilityState === 'visible') {
            refetchOrgModelPolicy();
          }
        }),
      )
      .then((unlisten) => {
        removeTauriFocusListener = unlisten;
      })
      .catch(() => undefined);
  }
}

function detachOrgModelPolicySyncListeners(): void {
  removeVisibilityListener?.();
  removeVisibilityListener = undefined;
  removeTauriFocusListener?.();
  removeTauriFocusListener = undefined;
}

export function useOrgModelPolicySync(): void {
  useEffect(() => {
    syncRefCount += 1;
    attachOrgModelPolicySyncListeners();

    return () => {
      syncRefCount -= 1;
      if (syncRefCount <= 0) {
        syncRefCount = 0;
        detachOrgModelPolicySyncListeners();
      }
    };
  }, []);
}
