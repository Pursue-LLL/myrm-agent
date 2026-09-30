/**
 * [INPUT]
 * @/services/desktopWakeRecovery::setupDesktopWakeRecovery (POS: 系统唤醒监听与自愈服务)
 *
 * [OUTPUT]
 * useDesktopWakeRecovery: 桌面端系统休眠/唤醒自动重连自愈 Hook。
 *
 * [POS]
 * 在 AppLayout 根生命周期挂载，开盖后毫秒级恢复会话状态与消息连接。
 */

import { useEffect } from 'react';
import { setupDesktopWakeRecovery } from '@/services/desktopWakeRecovery';

export function useDesktopWakeRecovery(): void {
  useEffect(() => {
    let cleanup: (() => void) | undefined;
    void setupDesktopWakeRecovery().then((unlisten) => {
      cleanup = unlisten;
    });

    return () => {
      if (cleanup) {
        cleanup();
      }
    };
  }, []);
}
