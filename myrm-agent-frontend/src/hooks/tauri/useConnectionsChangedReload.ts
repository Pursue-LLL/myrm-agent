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
 * 与主窗口同源加载本 Hook，实现切换后全窗口状态一致。
 * 事件回调先于发起方 invoke resolve 入队（Rust 端 emit 早于 command 返回），
 * 直接 reload 会打断发起方 resolve 后同步执行的 apply——延迟一拍让发起方
 * 先完成 UI 状态提交，再统一刷新。
 */

import { useEffect } from 'react';
import { isTauriRuntime } from '@/lib/deploy-mode';

/** 发起方 apply（同步链）完成后才刷新：兜住事件先于 invoke resolve 的入队顺序。 */
const RELOAD_DELAY_MS = 250;

export function useConnectionsChangedReload(): void {
  useEffect(() => {
    if (!isTauriRuntime()) {
      return undefined;
    }

    let unlisten: (() => void) | undefined;
    let disposed = false;
    let reloadTimer: number | undefined;

    void import('@tauri-apps/api/event')
      .then(({ listen }) => listen('app:connections-changed', () => {
        reloadTimer = window.setTimeout(() => {
          window.location.reload();
        }, RELOAD_DELAY_MS);
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
      if (reloadTimer !== undefined) {
        window.clearTimeout(reloadTimer);
      }
      if (unlisten) {
        unlisten();
      }
    };
  }, []);
}
