/**
 * [INPUT]
 * - `@/services/agent::getActiveSessions` (POS: 当前连接后端的进行中会话查询)
 *
 * [OUTPUT]
 * - `useActiveSessionsGuard`: 切断当前连接前的活跃会话守卫，返回 `guard`（有生成中会话时挂起 `proceed` 等待确认）与确认对话框状态。
 *
 * [POS]
 * 连接切换入口（添加/选择档案、断开回本地、发起云端登录、发现沙箱）共用的会话知情确认：有生成中会话时暂存继续动作并交给
 * `ActiveSessionsSwitchConfirmDialog`，确认后才执行；查询失败或超时（后端已停或不可达）直接放行，避免锁死切换路径；查询进行中的重复触发被忽略。
 */

import { useCallback, useRef, useState } from 'react';
import { getActiveSessions } from '@/services/agent';

/** 超过该时长无应答即视为当前连接不可达：切走不可达连接不应被前置查询卡住。 */
const QUERY_TIMEOUT_MS = 3000;

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('active sessions query timed out')), ms);
    promise.then(resolve, reject).finally(() => clearTimeout(timer));
  });
}

interface PendingConfirm {
  count: number;
  proceed: () => void;
}

export interface ActiveSessionsGuard {
  guard: (proceed: () => void) => Promise<void>;
  dialog: { open: boolean; count: number; onConfirm: () => void; onCancel: () => void };
}

/** `onDeclined`：用户在对话框中取消时回调，用于复位调用方的进行中状态。 */
export function useActiveSessionsGuard(onDeclined: () => void): ActiveSessionsGuard {
  const [pending, setPending] = useState<PendingConfirm | null>(null);

  // 查询期间入口可能被再次触发（按钮/开关无忙状态），单次飞行避免并发跑出多次切换。
  const queryingRef = useRef(false);

  const guard = useCallback(async (proceed: () => void): Promise<void> => {
    if (queryingRef.current) {
      return;
    }
    queryingRef.current = true;
    let running = 0;
    try {
      const { activeSessions } = await withTimeout(getActiveSessions(), QUERY_TIMEOUT_MS);
      running = activeSessions.length;
    } catch {
      // 放行：当前连接的后端不可达本身就是切换动机之一
    } finally {
      queryingRef.current = false;
    }
    if (running > 0) {
      setPending({ count: running, proceed });
      return;
    }
    proceed();
  }, []);

  const resolve = useCallback(
    (confirmed: boolean) => {
      // 先取值再 setState：updater 必须保持纯函数（StrictMode 双调不重复执行 proceed）
      const current = pending;
      setPending(null);
      if (!current) {
        return;
      }
      if (confirmed) {
        current.proceed();
      } else {
        onDeclined();
      }
    },
    [pending, onDeclined],
  );

  return {
    guard,
    dialog: {
      open: pending !== null,
      count: pending?.count ?? 0,
      onConfirm: () => resolve(true),
      onCancel: () => resolve(false),
    },
  };
}
