/**
 * [INPUT]
 * - `@/lib/tauri` (`isTauriEnvironment`, `listenTauriEvent`)
 *
 * [OUTPUT]
 * - `useCrashLoopGuard`: Tauri 模式下监听 `backend-crash-loop` 事件，
 *   当 watchdog 放弃自动重启时设置全局状态触发容灾 Dialog。
 *
 * [POS]
 * 补齐 watchdog → 前端 的事件链路。仅在 Tauri 模式下激活。
 */
import { useEffect, useState } from 'react';
import { isTauriEnvironment, listenTauriEvent } from '@/lib/tauri';

export function useCrashLoopGuard() {
  const [crashLoopActive, setCrashLoopActive] = useState(false);

  useEffect(() => {
    if (!isTauriEnvironment()) return;

    let unlisten: (() => void) | null = null;

    listenTauriEvent('backend-crash-loop', () => {
      setCrashLoopActive(true);
    })
      .then((fn) => {
        unlisten = fn;
      })
      .catch(() => undefined);

    return () => {
      unlisten?.();
    };
  }, []);

  const dismiss = () => setCrashLoopActive(false);

  return { crashLoopActive, dismiss };
}
