/**
 * CLI Agent React Hook（精简版）
 *
 * 提供 CLI Agent 的权限管理接口。
 * 消息发送已整合到 useChatStore，通过 actionMode='claude_code' 使用。
 */

import { useEffect, useCallback } from 'react';
import {
  useCLIAgentStore,
  usePermissionMode,
  usePendingPermissions,
  useCurrentPermissionRequest,
} from '@/store/useCLIAgentStore';
import type { PermissionMode } from '@/services/cli-agent';

// ============================================================================
// 权限模式快捷键 Hook
// ============================================================================

/**
 * 权限模式快捷键 Hook
 *
 * 监听 SHIFT+TAB 快捷键切换权限模式。
 */
export function usePermissionModeShortcut() {
  const cyclePermissionMode = useCLIAgentStore((state) => state.cyclePermissionMode);
  const permissionMode = usePermissionMode();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // SHIFT + TAB
      if (e.shiftKey && e.key === 'Tab') {
        e.preventDefault();
        cyclePermissionMode();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [cyclePermissionMode]);

  return permissionMode;
}

// ============================================================================
// 权限对话框 Hook
// ============================================================================

/**
 * 权限对话框 Hook
 *
 * 管理权限请求对话框的显示和响应。
 */
export function usePermissionDialog() {
  const pendingPermissions = usePendingPermissions();
  const currentRequest = useCurrentPermissionRequest();
  const respondPermission = useCLIAgentStore((state) => state.respondPermission);

  // 允许
  const allow = useCallback(
    (alwaysAllow = false) => {
      if (currentRequest) {
        respondPermission(currentRequest.requestId, true, alwaysAllow);
      }
    },
    [currentRequest, respondPermission],
  );

  // 拒绝
  const deny = useCallback(() => {
    if (currentRequest) {
      respondPermission(currentRequest.requestId, false, false);
    }
  }, [currentRequest, respondPermission]);

  return {
    isOpen: currentRequest !== null,
    request: currentRequest,
    allow,
    deny,
    pendingCount: pendingPermissions.length,
  };
}

// ============================================================================
// 主 Hook（整合用）
// ============================================================================

/**
 * CLI Agent Hook
 *
 * 整合权限管理功能。
 * 消息发送请使用 useChatStore + actionMode='claude_code'。
 *
 * @example
 * ```tsx
 * // 使用权限功能
 * const { permissionMode, cycleMode, setMode } = useCLIAgent();
 *
 * // 发送消息（使用现有聊天系统）
 * const { sendMessage, setActionMode } = useChatStore();
 * setActionMode('claude_code');  // 切换到 CLI Agent 模式
 * sendMessage('你的消息');        // 自动路由到 CLI Agent
 * ```
 */
export function useCLIAgent() {
  const store = useCLIAgentStore();
  const permissionMode = usePermissionMode();

  // 初始化
  useEffect(() => {
    store.initialize();
  }, []);

  // 切换权限模式
  const cycleMode = useCallback(async () => {
    await store.cyclePermissionMode();
  }, [store]);

  // 设置权限模式
  const setMode = useCallback(
    async (mode: PermissionMode) => {
      await store.setPermissionMode(mode);
    },
    [store],
  );

  return {
    // 状态
    permissionMode,
    pendingPermissions: store.pendingPermissions,
    currentSessionId: store.currentSessionId,

    // 操作
    setMode,
    cycleMode,
    setCurrentSessionId: store.setCurrentSessionId,
  };
}
