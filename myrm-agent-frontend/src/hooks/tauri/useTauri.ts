import { useState, useEffect } from 'react';

type InvokeFn = <T>(cmd: string, args?: Record<string, unknown>) => Promise<T>;

/**
 * Tauri 运行时探测 hook。
 *
 * 返回:
 * - `isTauri`: 当前是否运行在 Tauri 桌面容器内
 * - `invoke`: 直接调用 Tauri IPC command（非 Tauri 环境为 null）
 */
export function useTauri() {
  const [isTauri, setIsTauri] = useState(false);
  const [invoke, setInvoke] = useState<InvokeFn | null>(null);

  useEffect(() => {
    if (typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window) {
      setIsTauri(true);
      import('@tauri-apps/api/core')
        .then((mod) => setInvoke(() => mod.invoke))
        .catch(() => setInvoke(null));
    }
  }, []);

  return { isTauri, invoke };
}
