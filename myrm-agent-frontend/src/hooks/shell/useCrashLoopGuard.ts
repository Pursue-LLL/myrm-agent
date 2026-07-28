/**
 * [INPUT]
 * - `@/lib/tauri` (`isTauriEnvironment`, `listenTauriEvent`)
 *
 * [OUTPUT]
 * - `useCrashLoopGuard`: Tauri 模式下监听 `backend-crash-loop` 事件，
 *   当 watchdog 放弃自动重启时设置全局状态触发容灾 Dialog。
 *   携带可选的错误消息 payload 用于前端展示崩溃原因。
 *
 * [POS]
 * watchdog → 前端 的事件链路。仅在 Tauri 模式下激活。
 */
import { useEffect, useState } from 'react';
import { isTauriEnvironment, listenTauriEvent } from '@/lib/tauri';

export function useCrashLoopGuard() {
  const [crashLoopActive, setCrashLoopActive] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!isTauriEnvironment()) return;

    let unlisten: (() => void) | null = null;

    listenTauriEvent('backend-crash-loop', (event: unknown) => {
      const payload = (event as { payload?: unknown })?.payload;
      const msg = typeof payload === 'string' && payload.length > 0 ? payload : null;
      setErrorMessage(msg);
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

  const dismiss = () => {
    setCrashLoopActive(false);
    setErrorMessage(null);
  };

  return { crashLoopActive, errorMessage, dismiss };
}
