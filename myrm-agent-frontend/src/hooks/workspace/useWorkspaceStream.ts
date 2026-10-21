'use client';

import { useEffect } from 'react';
import { connectionManager } from '@/services/ConnectionManager';
import { resolveE2eApiBase } from '@/lib/deploy-mode';
import useAuthStore from '@/store/useAuthStore';

/**
 * Maintains the multiplexed workspace SSE connection (/workspace/stream).
 * Required for multiplexed agent-stream chunks to reach multiplexChunkBridge.
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
