/**
 * 部署模式 React Hook
 *
 * 提供响应式的部署模式检测
 */

import { useEffect, useState } from 'react';

import { type DeployMode, getDeployMode, isLocalMode, isSandbox } from '@/lib/deploy-mode';

interface DeployModeState {
  mode: DeployMode;
  /** 是否为本地模式（TAURI 或 LOCAL） */
  isLocal: boolean;
  isSandbox: boolean;
  isLoading: boolean;
}

/**
 * 获取当前部署模式的 Hook
 *
 * @example
 * ```tsx
 * const { mode, isLocal, isSandbox } = useDeployMode();
 *
 * if (isLocal) {
 *   // 显示本地模式专属设置
 * }
 * ```
 */
export function useDeployMode(): DeployModeState {
  const [state, setState] = useState<DeployModeState>({
    mode: 'sandbox',
    isLocal: false,
    isSandbox: true,
    isLoading: true,
  });

  useEffect(() => {
    const local = isLocalMode();
    setState({
      mode: getDeployMode(),
      isLocal: local,
      isSandbox: isSandbox(),
      isLoading: false,
    });
  }, []);

  return state;
}
