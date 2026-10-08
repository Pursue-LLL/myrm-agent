/**
 * [INPUT]
 * - `@/services/agent::getActiveSessions` (POS: 本地后端进行中会话查询)
 *
 * [OUTPUT]
 * - `useActiveSessionsGuard`: 切断当前连接前的活跃会话守卫，返回 `guard`（有生成中会话时挂起 `proceed` 等待确认）与确认对话框状态。
 *
 * [POS]
 * 连接切换入口（切换档案、发起云端登录、发现沙箱）共用的会话知情确认：有生成中会话时暂存继续动作并交给
 * `ActiveSessionsSwitchConfirmDialog`，确认后才执行；查询失败（后端已停或不可达）直接放行，避免锁死切换路径。
 */

import { useCallback, useState } from 'react';
import { getActiveSessions } from '@/services/agent';

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

  const guard = useCallback(async (proceed: () => void): Promise<void> => {
    try {
      const { activeSessions } = await getActiveSessions();
      if (activeSessions.length > 0) {
        setPending({ count: activeSessions.length, proceed });
        return;
      }
    } catch {
      // 放行：本地后端不可达本身就是切换动机之一
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
