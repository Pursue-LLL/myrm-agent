/**
 * CLI Agent 服务
 *
 * 通过 Tauri IPC 调用 CLI Agent 功能。
 * 这是前端与 Rust 后端 + Node.js Sidecar 的通信接口。
 */

import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';

// ============================================================================
// 类型定义
// ============================================================================

/** 权限模式 */
export type PermissionMode = 'explore' | 'ask' | 'auto';

/** 会话状态 */
export type SessionStatus = 'pending' | 'in_progress' | 'needs_review' | 'completed' | 'error';

/** 适配器信息 */
export interface AdapterInfo {
  id: string;
  name: string;
  available: boolean;
  version?: string;
}

/** 会话信息 */
export interface CLISession {
  id: string;
  agentId: string;
  title?: string;
  cwd: string;
  status: SessionStatus;
  permissionMode: PermissionMode;
  sdkSessionId?: string;
  createdAt: number;
  updatedAt: number;
  flagged: boolean;
}

/** 权限请求 */
export interface PermissionRequest {
  requestId: string;
  toolName: string;
  command: string;
  isDangerous: boolean;
}

/** Agent 消息类型 */
export type AgentMessageType =
  | 'text'
  | 'thought'
  | 'tool_call_start'
  | 'tool_call_result'
  | 'permission_request'
  | 'session_status'
  | 'error'
  | 'done';

/** Agent 消息 */
export interface AgentMessage {
  type: AgentMessageType;
  content?: string;
  msgId?: string;
  callId?: string;
  toolName?: string;
  arguments?: Record<string, unknown>;
  status?: 'running' | 'completed' | 'failed';
  sessionStatus?: SessionStatus;
  permissionRequest?: PermissionRequest;
  error?: string;
}

// ============================================================================
// Agent 检测
// ============================================================================

/**
 * 检测可用的 CLI Agent
 */
export async function detectAgents(): Promise<string[]> {
  return invoke<string[]>('detect_agents');
}

/**
 * 获取所有适配器信息
 */
export async function listAgentAdapters(): Promise<AdapterInfo[]> {
  return invoke<AdapterInfo[]>('list_agent_adapters');
}

// ============================================================================
// 会话管理
// ============================================================================

/**
 * 创建 Agent 会话
 */
export async function createAgentSession(
  agentId: string,
  cwd: string,
  permissionMode?: PermissionMode,
): Promise<CLISession> {
  return invoke<CLISession>('create_agent_session', {
    agentId,
    cwd,
    permissionMode,
  });
}

/**
 * 获取会话列表
 */
export async function listAgentSessions(): Promise<CLISession[]> {
  return invoke<CLISession[]>('list_agent_sessions');
}

/**
 * 获取单个会话
 */
export async function getAgentSession(sessionId: string): Promise<CLISession | null> {
  return invoke<CLISession | null>('get_agent_session', { sessionId });
}

/**
 * 删除会话
 */
export async function deleteAgentSession(sessionId: string): Promise<void> {
  return invoke<void>('delete_agent_session', { sessionId });
}

/**
 * 恢复会话
 *
 * 使用 CLI 的原生会话恢复功能（如 Claude SDK 的 resume 参数）
 * @param sessionId 会话 ID
 * @returns 恢复后的会话信息
 */
export async function resumeAgentSession(sessionId: string): Promise<CLISession> {
  return invoke<CLISession>('resume_agent_session', { sessionId });
}

// ============================================================================
// 消息发送
// ============================================================================

/**
 * 发送消息到 Agent
 *
 * 消息通过 Tauri 事件流式返回。
 * 使用 listenAgentMessages 监听响应。
 */
export async function sendAgentMessage(sessionId: string, prompt: string): Promise<void> {
  return invoke<void>('send_agent_message', { sessionId, prompt });
}

/**
 * 停止 Agent 消息流
 */
export async function stopAgentMessage(sessionId: string): Promise<void> {
  return invoke<void>('stop_agent_message', { sessionId });
}

/**
 * 监听 Agent 消息事件
 *
 * @param sessionId 会话 ID
 * @param callback 消息回调
 * @returns 取消监听函数
 */
export async function listenAgentMessages(
  sessionId: string,
  callback: (message: AgentMessage) => void,
): Promise<UnlistenFn> {
  return listen<AgentMessage>(`agent:message:${sessionId}`, (event) => {
    callback(event.payload);
  });
}

/**
 * 监听 Agent 权限请求事件
 */
export async function listenAgentPermission(
  sessionId: string,
  callback: (request: PermissionRequest) => void,
): Promise<UnlistenFn> {
  return listen<{
    session_id: string;
    request_id: string;
    tool_name: string;
    command: string;
    is_dangerous: boolean;
  }>(`agent:permission:${sessionId}`, (event) => {
    callback({
      requestId: event.payload.request_id,
      toolName: event.payload.tool_name,
      command: event.payload.command,
      isDangerous: event.payload.is_dangerous,
    });
  });
}

/**
 * 监听 Agent 状态变更事件
 */
export async function listenAgentStatus(
  sessionId: string,
  callback: (status: SessionStatus, error?: string) => void,
): Promise<UnlistenFn> {
  return listen<{ session_id: string; status: string; error?: string }>(`agent:status:${sessionId}`, (event) => {
    callback(event.payload.status as SessionStatus, event.payload.error);
  });
}

// ============================================================================
// 权限管理
// ============================================================================

/**
 * 响应权限请求
 */
export async function respondAgentPermission(
  sessionId: string,
  requestId: string,
  allowed: boolean,
  alwaysAllow: boolean = false,
): Promise<void> {
  return invoke<void>('respond_agent_permission', {
    sessionId,
    requestId,
    allowed,
    alwaysAllow,
  });
}

/**
 * 获取当前权限模式
 */
export async function getPermissionMode(): Promise<PermissionMode> {
  return invoke<PermissionMode>('get_permission_mode');
}

/**
 * 设置权限模式
 */
export async function setPermissionMode(mode: PermissionMode): Promise<void> {
  return invoke<void>('set_permission_mode', { mode });
}

/**
 * 循环切换权限模式（SHIFT+TAB）
 */
export async function cyclePermissionMode(): Promise<PermissionMode> {
  return invoke<PermissionMode>('cycle_permission_mode');
}

// ============================================================================
// 工具函数
// ============================================================================

/**
 * 权限模式显示名称
 */
export function getPermissionModeDisplayName(mode: PermissionMode): string {
  switch (mode) {
    case 'explore':
      return 'Explore';
    case 'ask':
      return 'Ask to Edit';
    case 'auto':
      return 'Auto';
  }
}

/**
 * 会话状态显示名称
 */
export function getSessionStatusDisplayName(status: SessionStatus): string {
  switch (status) {
    case 'pending':
      return 'Pending';
    case 'in_progress':
      return 'In Progress';
    case 'needs_review':
      return 'Needs Review';
    case 'completed':
      return 'Completed';
    case 'error':
      return 'Error';
  }
}
