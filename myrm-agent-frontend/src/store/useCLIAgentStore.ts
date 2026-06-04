/**
 * CLI Agent Store（精简版）
 *
 * 管理 CLI Agent 的辅助状态：
 * - 权限模式 (Explore/Ask/Auto)
 * - 待处理的权限请求
 *
 * 注意：消息已整合到 useChatStore，通过 actionMode='claude_code' 使用。
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md（如有）
 *
 * [INPUT]
 * - zustand: 状态管理库
 * - @/services/cli-agent::getPermissionMode, setPermissionMode, cyclePermissionMode,
 *   respondAgentPermission, listAgentSessions, resumeAgentSession, deleteAgentSession
 *   (POS: CLI Agent Tauri IPC 服务)
 * - @/services/cli-agent::PermissionMode, PermissionRequest, CLISession
 *   (POS: CLI Agent 类型定义)
 *
 * [OUTPUT]
 * - useCLIAgentStore: CLI Agent 状态 Store
 *   - permissionMode: 当前权限模式 (explore/ask/auto)
 *   - pendingPermissions: 待处理的权限请求列表
 *   - currentSessionId: 当前 CLI 会话 ID
 *   - workingDirectory: CLI 工作目录
 *   - sessions: 历史会话列表
 *   - sessionsLoading: 会话列表加载状态
 *   - initialize(): 初始化权限模式和会话列表
 *   - setPermissionMode(): 设置权限模式
 *   - cyclePermissionMode(): 循环切换权限模式
 *   - addPermissionRequest(): 添加权限请求
 *   - respondPermission(): 响应权限请求（批准/拒绝）
 *   - setWorkingDirectory(): 设置工作目录
 *   - refreshSessions(): 刷新会话列表
 *   - resumeSession(): 恢复历史会话
 *   - deleteSession(): 删除历史会话
 * - useWorkingDirectory: 选择器，获取工作目录
 * - useCLISessions: 选择器，获取历史会话列表
 * - useCLISessionsLoading: 选择器，获取会话加载状态
 *
 * [POS]
 * CLI Agent 状态管理。管理权限模式（三级：Explore/Ask/Auto）和
 * 待处理的权限请求。消息状态已整合到 useChatStore，本 Store 仅
 * 管理 CLI Agent 特有的辅助状态。被 ToolCallApproval 组件使用。
 */

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import {
  getAgentSidecarStatus,
  getPermissionMode,
  setPermissionMode as setPermissionModeAPI,
  cyclePermissionMode as cyclePermissionModeAPI,
  respondAgentPermission,
  listAgentSessions,
  resumeAgentSession,
  deleteAgentSession,
  type PermissionMode,
  type PermissionRequest,
  type CLISession,
} from '@/services/cli-agent';

// ============================================================================
// 状态类型
// ============================================================================

interface CLIAgentState {
  // ==================== 权限状态 ====================
  /** 权限模式 */
  permissionMode: PermissionMode;
  /** 待处理的权限请求 */
  pendingPermissions: PermissionRequest[];
  /** 当前会话 ID */
  currentSessionId: string | null;
  /** CLI 工作目录 */
  workingDirectory: string | null;

  // ==================== 会话列表状态 ====================
  /** 历史会话列表 */
  sessions: CLISession[];
  /** 会话列表加载状态 */
  sessionsLoading: boolean;
  /** Agent Runner Sidecar：ready | starting | failed */
  sidecarStatus: 'unknown' | 'ready' | 'starting' | 'failed';
  /** Sidecar 启动失败时的错误信息 */
  sidecarError: string | null;

  // ==================== 操作 ====================
  /** 初始化（获取当前权限模式 + 会话列表） */
  initialize: () => Promise<void>;
  /** 设置权限模式 */
  setPermissionMode: (mode: PermissionMode) => Promise<void>;
  /** 循环切换权限模式 */
  cyclePermissionMode: () => Promise<void>;
  /** 添加待处理的权限请求 */
  addPermissionRequest: (request: PermissionRequest) => void;
  /** 响应权限请求 */
  respondPermission: (requestId: string, allowed: boolean, alwaysAllow?: boolean) => Promise<void>;
  /** 设置当前会话 ID */
  setCurrentSessionId: (sessionId: string | null) => void;
  /** 设置工作目录 */
  setWorkingDirectory: (cwd: string | null) => void;

  // ==================== 会话管理操作 ====================
  /** 刷新会话列表 */
  refreshSessions: () => Promise<void>;
  /** 恢复会话 */
  resumeSession: (sessionId: string) => Promise<CLISession | null>;
  /** 删除会话 */
  deleteSession: (sessionId: string) => Promise<boolean>;
  /** 刷新 Sidecar 状态（Tauri 桌面端） */
  refreshSidecarStatus: () => Promise<void>;
  setSidecarReady: () => void;
  setSidecarFailed: (message: string) => void;
}

// ============================================================================
// Store 实现
// ============================================================================

export const useCLIAgentStore = create<CLIAgentState>()(
  devtools(
    (set, get) => ({
      // ==================== 初始状态 ====================
      permissionMode: 'ask',
      pendingPermissions: [],
      currentSessionId: null,
      workingDirectory: null,
      sessions: [],
      sessionsLoading: false,
      sidecarStatus: 'unknown',
      sidecarError: null,

      // ==================== 操作 ====================
      initialize: async () => {
        try {
          const [mode, sessions] = await Promise.all([getPermissionMode(), listAgentSessions().catch(() => [])]);
          set({ permissionMode: mode, sessions });
          await get().refreshSidecarStatus();
        } catch {
          // Tauri 环境不可用时忽略
        }
      },

      refreshSidecarStatus: async () => {
        try {
          const raw = await getAgentSidecarStatus();
          if (raw === 'ready') {
            set({ sidecarStatus: 'ready', sidecarError: null });
          } else if (raw === 'starting') {
            set({ sidecarStatus: 'starting', sidecarError: null });
          } else if (raw.startsWith('failed:')) {
            set({ sidecarStatus: 'failed', sidecarError: raw.slice('failed:'.length) });
          } else {
            set({ sidecarStatus: 'unknown', sidecarError: null });
          }
        } catch {
          set({ sidecarStatus: 'unknown', sidecarError: null });
        }
      },

      setSidecarReady: () => set({ sidecarStatus: 'ready', sidecarError: null }),

      setSidecarFailed: (message) => set({ sidecarStatus: 'failed', sidecarError: message }),

      setPermissionMode: async (mode) => {
        try {
          await setPermissionModeAPI(mode);
          set({ permissionMode: mode });
        } catch (error) {
          console.error('Failed to set permission mode:', error);
        }
      },

      cyclePermissionMode: async () => {
        try {
          const newMode = await cyclePermissionModeAPI();
          set({ permissionMode: newMode });
        } catch (error) {
          console.error('Failed to cycle permission mode:', error);
        }
      },

      addPermissionRequest: (request) => {
        set((state) => ({
          pendingPermissions: [...state.pendingPermissions, request],
        }));
      },

      respondPermission: async (requestId, allowed, alwaysAllow = false) => {
        const { currentSessionId } = get();
        if (!currentSessionId) return;

        try {
          await respondAgentPermission(currentSessionId, requestId, allowed, alwaysAllow);

          // 移除已响应的权限请求
          set((state) => ({
            pendingPermissions: state.pendingPermissions.filter((p) => p.requestId !== requestId),
          }));
        } catch (error) {
          console.error('Failed to respond permission:', error);
        }
      },

      setCurrentSessionId: (sessionId) => {
        set({ currentSessionId: sessionId });
      },

      setWorkingDirectory: (cwd) => {
        set({ workingDirectory: cwd });
      },

      // ==================== 会话管理操作 ====================
      refreshSessions: async () => {
        set({ sessionsLoading: true });
        try {
          const sessions = await listAgentSessions();
          set({ sessions, sessionsLoading: false });
        } catch (error) {
          console.error('Failed to refresh sessions:', error);
          set({ sessionsLoading: false });
        }
      },

      resumeSession: async (sessionId) => {
        try {
          const session = await resumeAgentSession(sessionId);
          set({
            currentSessionId: session.id,
            workingDirectory: session.cwd,
          });
          // 刷新会话列表以更新 lastUsedAt
          get().refreshSessions();
          return session;
        } catch (error) {
          console.error('Failed to resume session:', error);
          return null;
        }
      },

      deleteSession: async (sessionId) => {
        try {
          await deleteAgentSession(sessionId);
          // 从列表中移除
          set((state) => ({
            sessions: state.sessions.filter((s) => s.id !== sessionId),
            // 如果删除的是当前会话，清空当前会话状态
            ...(state.currentSessionId === sessionId ? { currentSessionId: null, workingDirectory: null } : {}),
          }));
          return true;
        } catch (error) {
          console.error('Failed to delete session:', error);
          return false;
        }
      },
    }),
    { name: 'cli-agent-store' },
  ),
);

// ============================================================================
// 选择器
// ============================================================================

/** 获取权限模式 */
export const usePermissionMode = () => useCLIAgentStore((state) => state.permissionMode);

/** 获取待处理的权限请求 */
export const usePendingPermissions = () => useCLIAgentStore((state) => state.pendingPermissions);

/** 获取第一个待处理的权限请求（用于对话框） */
export const useCurrentPermissionRequest = () =>
  useCLIAgentStore((state) => (state.pendingPermissions.length > 0 ? state.pendingPermissions[0] : null));

/** 获取 CLI 工作目录 */
export const useWorkingDirectory = () => useCLIAgentStore((state) => state.workingDirectory);

/** 获取历史会话列表 */
export const useCLISessions = () => useCLIAgentStore((state) => state.sessions);

/** 获取会话列表加载状态 */
export const useCLISessionsLoading = () => useCLIAgentStore((state) => state.sessionsLoading);
