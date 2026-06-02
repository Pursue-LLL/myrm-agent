/**
 * Tauri 后端管理 Hook
 *
 * 提供 React Hook 来管理 Tauri 后端的启动、停止和健康检查。
 */

import { useCallback, useEffect, useState } from 'react';

import { isTauriEnvironment, tauriBackend } from '@/lib/tauri';

interface BackendStatus {
  isRunning: boolean;
  isHealthy: boolean;
  isChecking: boolean;
  error: string | null;
}

interface UseTauriBackendReturn extends BackendStatus {
  startBackend: () => Promise<void>;
  stopBackend: () => Promise<void>;
  checkHealth: () => Promise<void>;
}

/**
 * Tauri 后端管理 Hook
 *
 * @example
 * ```tsx
 * const { isRunning, isHealthy, startBackend, checkHealth } = useTauriBackend();
 *
 * useEffect(() => {
 *   if (!isRunning) {
 *     startBackend();
 *   }
 * }, [isRunning]);
 * ```
 */
export function useTauriBackend(): UseTauriBackendReturn {
  const [status, setStatus] = useState<BackendStatus>({
    isRunning: false,
    isHealthy: false,
    isChecking: false,
    error: null,
  });

  const checkHealth = useCallback(async () => {
    if (!isTauriEnvironment()) {
      return;
    }

    setStatus((prev) => ({ ...prev, isChecking: true, error: null }));

    try {
      const healthy = await tauriBackend.checkHealth();
      setStatus({
        isRunning: true,
        isHealthy: healthy,
        isChecking: false,
        error: null,
      });
    } catch (error) {
      setStatus({
        isRunning: false,
        isHealthy: false,
        isChecking: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      });
    }
  }, []);

  const startBackend = useCallback(async () => {
    if (!isTauriEnvironment()) {
      return;
    }

    setStatus((prev) => ({ ...prev, error: null }));

    try {
      await tauriBackend.start();
      // 等待后端启动
      await new Promise((resolve) => setTimeout(resolve, 2000));
      await checkHealth();
    } catch (error) {
      setStatus((prev) => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Failed to start backend',
      }));
    }
  }, [checkHealth]);

  const stopBackend = useCallback(async () => {
    if (!isTauriEnvironment()) {
      return;
    }

    try {
      await tauriBackend.stop();
      setStatus({
        isRunning: false,
        isHealthy: false,
        isChecking: false,
        error: null,
      });
    } catch (error) {
      setStatus((prev) => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Failed to stop backend',
      }));
    }
  }, []);

  // 定期健康检查（每 30 秒）
  useEffect(() => {
    if (!isTauriEnvironment()) {
      return;
    }

    const interval = setInterval(() => {
      checkHealth();
    }, 30000);

    // 初始检查
    checkHealth();

    return () => clearInterval(interval);
  }, [checkHealth]);

  return {
    ...status,
    startBackend,
    stopBackend,
    checkHealth,
  };
}
