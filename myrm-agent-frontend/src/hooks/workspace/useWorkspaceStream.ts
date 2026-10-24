'use client';

import { useEffect } from 'react';
import { connectionManager } from '@/services/ConnectionManager';
import { resolveE2eApiBase } from '@/lib/deploy-mode';
import useAuthStore from '@/store/useAuthStore';

/**
 * Maintains the multiplexed workspace SSE connection (/workspace/stream).
 * Supplies live session_status (sidebar generating/idle) and the reconnect pulse used for resync.
 * 回合正文不走这里：agent-stream 正文固定由 POST 响应体（SSE）承载。
 */
export function useWorkspaceStream(): void {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  useEffect(() => {
    if (!isAuthenticated) {
      connectionManager.disconnect();
      return;
    }

    connectionManager.connect();

    const resync = () => {
      connectionManager.connect();
    };

    window.addEventListener('myrm_e2e_runtime_ready', resync);
    const poll = window.setInterval(() => {
      if (resolveE2eApiBase()) {
        resync();
      }
    }, 1500);

    return () => {
      window.clearInterval(poll);
      window.removeEventListener('myrm_e2e_runtime_ready', resync);
      connectionManager.disconnect();
    };
  }, [isAuthenticated]);
}
