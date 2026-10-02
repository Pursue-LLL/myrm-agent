/**
 * [INPUT]
 * @tauri-apps/api/event::listen (POS: Tauri 原生事件接收通道)
 * @/lib/deploy-mode::isTauriRuntime (POS: Tauri 运行时排他判定)
 *
 * [OUTPUT]
 * useConnectionsChangedReload: 连接态变更全局 reload Hook。
 *
 * [POS]
 * 在 AppLayout 根生命周期挂载。监听 Rust 端 `app:connections-changed`
 * （连接档案切换完成时广播），统一驱动当前窗口 reload。session windows
 * 与主窗口同源加载本 Hook，实现切换后全窗口状态一致，替代旧的手动
 * 逐处 reload（主窗口 reload 不再传播到独立 WebviewWindow 的问题由此解决）。
 */

import { useEffect } from 'react';
import { isTauriRuntime } from '@/lib/deploy-mode';

export function useConnectionsChangedReload(): void {
  useEffect(() => {
    if (!isTauriRuntime()) {
      return undefined;
    }

    let unlisten: (() => void) | undefined;
    let disposed = false;

    void import('@tauri-apps/api/event')
      .then(({ listen }) => listen('app:connections-changed', () => {
        window.location.reload();
      }))
      .then((fn) => {
        if (disposed) {
          fn();
        } else {
          unlisten = fn;
        }
      })
      .catch((err) => {
        console.warn('[ConnectionsChangedReload] Failed to subscribe to app:connections-changed:', err);
      });

    return () => {
      disposed = true;
      if (unlisten) {
        unlisten();
      }
    };
  }, []);
}
