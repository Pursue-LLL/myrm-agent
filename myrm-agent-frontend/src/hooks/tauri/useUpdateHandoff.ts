'use client';

/**
 * [POS] Tauri 桌面端更新交接结果感知 Hook
 *
 * 管理跨应用重启/更新安装的 Handoff 事务状态：
 * 1. 发起安装前写入期望版本（targetVersion）与当前版本（fromVersion）
 * 2. 重启冷启动时读取并原子校验：
 *    - 若 currentVersion === targetVersion: 判定更新成功，触发 success 回调
 *    - 若 currentVersion !== targetVersion 且未超时（TTL 10min）: 判定更新未生效/失败，触发 failure 回调
 *    - 若已超过 TTL: 视为过期残留事务静默丢弃
 * 3. 非 Tauri 运行环境安全 no-op。
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { isTauriRuntime } from '@/lib/deploy-mode';

export const UPDATE_HANDOFF_STORAGE_KEY = 'myrm-pending-update-handoff';
export const UPDATE_HANDOFF_TTL_MS = 10 * 60 * 1000; // 10 minutes

export interface UpdateHandoffRecord {
  fromVersion: string;
  targetVersion: string;
  timestamp: number;
}

export type UpdateHandoffResultType = 'success' | 'failure' | null;

export interface UpdateHandoffResult {
  type: UpdateHandoffResultType;
  fromVersion: string;
  targetVersion: string;
  currentVersion: string;
}

export interface UseUpdateHandoffOptions {
  onSuccess?: (result: UpdateHandoffResult) => void;
  onFailure?: (result: UpdateHandoffResult) => void;
}

export interface UseUpdateHandoffReturn {
  result: UpdateHandoffResult | null;
  dismiss: () => void;
  recordHandoff: (fromVersion: string, targetVersion: string) => void;
}

export function saveUpdateHandoff(fromVersion: string, targetVersion: string): void {
  if (typeof window === 'undefined') {
    return;
  }
  const record: UpdateHandoffRecord = {
    fromVersion,
    targetVersion,
    timestamp: Date.now(),
  };
  try {
    window.localStorage.setItem(UPDATE_HANDOFF_STORAGE_KEY, JSON.stringify(record));
  } catch {
    /* quota exceeded or private mode guard */
  }
}

export function readUpdateHandoff(): UpdateHandoffRecord | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(UPDATE_HANDOFF_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as Partial<UpdateHandoffRecord>;
    if (
      typeof parsed?.fromVersion === 'string' &&
      typeof parsed?.targetVersion === 'string' &&
      typeof parsed?.timestamp === 'number'
    ) {
      return parsed as UpdateHandoffRecord;
    }
    return null;
  } catch {
    return null;
  }
}

export function clearUpdateHandoff(): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.removeItem(UPDATE_HANDOFF_STORAGE_KEY);
  } catch {
    /* guard */
  }
}

async function getAppVersion(): Promise<string | null> {
  if (!isTauriRuntime()) {
    return null;
  }
  try {
    const { getVersion } = await import('@tauri-apps/api/app');
    return await getVersion();
  } catch {
    return null;
  }
}

export function evaluateUpdateHandoff(
  record: UpdateHandoffRecord | null,
  currentVersion: string,
  now = Date.now(),
): UpdateHandoffResult | null {
  if (!record) {
    return null;
  }

  // Check TTL expiration
  if (now - record.timestamp > UPDATE_HANDOFF_TTL_MS) {
    return null;
  }

  if (currentVersion === record.targetVersion) {
    return {
      type: 'success',
      fromVersion: record.fromVersion,
      targetVersion: record.targetVersion,
      currentVersion,
    };
  }

  // If version has not changed to targetVersion within TTL window
  return {
    type: 'failure',
    fromVersion: record.fromVersion,
    targetVersion: record.targetVersion,
    currentVersion,
  };
}

export function useUpdateHandoff(options: UseUpdateHandoffOptions = {}): UseUpdateHandoffReturn {
  const { onSuccess, onFailure } = options;
  const [result, setResult] = useState<UpdateHandoffResult | null>(null);
  const checkedRef = useRef(false);

  useEffect(() => {
    if (checkedRef.current || !isTauriRuntime()) {
      return;
    }
    checkedRef.current = true;

    void (async () => {
      const record = readUpdateHandoff();
      if (!record) {
        return;
      }

      // Always clear localStorage immediately to avoid repeated prompts on subsequent reloads
      clearUpdateHandoff();

      let currentVersion: string | null = null;
      try {
        currentVersion = await getAppVersion();
      } catch {
        return;
      }
      if (!currentVersion) {
        return;
      }

      const evalResult = evaluateUpdateHandoff(record, currentVersion);
      if (!evalResult) {
        return;
      }

      setResult(evalResult);
      if (evalResult.type === 'success') {
        onSuccess?.(evalResult);
      } else if (evalResult.type === 'failure') {
        onFailure?.(evalResult);
      }
    })();
  }, [onSuccess, onFailure]);

  const dismiss = useCallback(() => {
    setResult(null);
  }, []);

  const recordHandoff = useCallback((fromVersion: string, targetVersion: string) => {
    saveUpdateHandoff(fromVersion, targetVersion);
  }, []);

  return {
    result,
    dismiss,
    recordHandoff,
  };
}
