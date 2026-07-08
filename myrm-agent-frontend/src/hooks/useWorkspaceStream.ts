'use client';

import { useEffect } from 'react';
import { connectionManager } from '@/services/ConnectionManager';
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
    return () => {
      connectionManager.disconnect();
    };
  }, [isAuthenticated]);
}
