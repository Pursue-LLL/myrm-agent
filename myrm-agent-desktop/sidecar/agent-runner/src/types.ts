/**
 * CLI Agent Runner 类型定义
 *
 * 定义 Tauri ↔ Sidecar 之间的 JSON-RPC 通信协议。
 * 借鉴 Claude-Cowork 和 craft-agents 的设计。
 */

// ============================================================================
// JSON-RPC 协议
// ============================================================================

/**
 * JSON-RPC 请求（Tauri → Sidecar）
 */
export interface RPCRequest {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params?: Record<string, unknown>;
}

/**
 * JSON-RPC 响应（Sidecar → Tauri）
 */
export interface RPCResponse {
  jsonrpc: "2.0";
  id: number;
  result?: unknown;
  error?: {
    code: number;
    message: string;
    data?: unknown;
  };
}

/**
 * JSON-RPC 通知（Sidecar → Tauri，无需响应）
 */
export interface RPCNotification {
  jsonrpc: "2.0";
  method: string;
  params?: Record<string, unknown>;
}

// ============================================================================
// RPC 方法
// ============================================================================

export type RPCMethod =
  | "detect_agents" // 检测可用的 CLI Agent
  | "create_session" // 创建会话
  | "send_message" // 发送消息
  | "respond_permission" // 响应权限请求
  | "stop_session" // 停止会话
  | "set_permission_mode"; // 设置权限模式

// ============================================================================
// 会话相关
// ============================================================================

/**
 * 权限模式（借鉴 craft-agents）
 */
export type PermissionMode = "explore" | "ask" | "auto";

/**
 * 会话配置
 */
export interface SessionConfig {
  /** 工作目录 */
  cwd: string;
  /** 权限模式 */
  permissionMode: PermissionMode;
  /** 恢复的会话 ID */
  resumeSessionId?: string;
}

/**
 * 会话状态
 */
export type SessionStatus =
  | "pending"
  | "in_progress"
  | "needs_review"
  | "completed"
  | "error";

// ============================================================================
// 事件类型（Sidecar → Tauri 通知）
// ============================================================================

/**
 * 流式消息事件
 */
export interface StreamMessageEvent {
  type: "stream.message";
  sessionId: string;
  message: SDKMessageLike;
}

/**
 * 权限请求事件
 */
export interface PermissionRequestEvent {
  type: "permission.request";
  sessionId: string;
  requestId: string;
  toolName: string;
  command: string;
  isDangerous: boolean;
}

/**
 * 会话状态变更事件
 */
export interface SessionStatusEvent {
  type: "session.status";
  sessionId: string;
  status: SessionStatus;
  title?: string;
  error?: string;
}

export type AgentEvent =
  | StreamMessageEvent
  | PermissionRequestEvent
  | SessionStatusEvent;

// ============================================================================
// SDK 消息类型（简化版，参考 @anthropic-ai/claude-agent-sdk）
// ============================================================================

/**
 * SDK 消息基础类型
 */
export interface SDKMessageBase {
  type: string;
}

/**
 * 系统消息（初始化）
 */
export interface SDKSystemMessage extends SDKMessageBase {
  type: "system";
  subtype: "init" | "error";
  session_id?: string;
  message?: string;
}

/**
 * 助手消息
 */
export interface SDKAssistantMessage extends SDKMessageBase {
  type: "assistant";
  message: {
    id: string;
    role: "assistant";
    content: ContentBlock[];
    model: string;
    stop_reason?: string;
  };
}

/**
 * 用户消息
 */
export interface SDKUserMessage extends SDKMessageBase {
  type: "user";
  message: {
    role: "user";
    content: ContentBlock[];
  };
}

/**
 * 结果消息
 */
export interface SDKResultMessage extends SDKMessageBase {
  type: "result";
  subtype: "success" | "error" | "interrupted";
  cost_usd?: number;
  duration_ms?: number;
  error?: string;
}

/**
 * 内容块类型
 */
export type ContentBlock =
  | { type: "text"; text: string }
  | { type: "tool_use"; id: string; name: string; input: unknown }
  | { type: "tool_result"; tool_use_id: string; content: string; is_error?: boolean }
  | { type: "thinking"; thinking: string };

/**
 * SDK 消息联合类型
 */
export type SDKMessageLike =
  | SDKSystemMessage
  | SDKAssistantMessage
  | SDKUserMessage
  | SDKResultMessage;

// ============================================================================
// 危险命令（借鉴 craft-agents）
// ============================================================================

export const DANGEROUS_COMMANDS = new Set([
  // 文件删除
  "rm",
  "rmdir",
  "del",
  "unlink",
  // 权限提升
  "sudo",
  "su",
  "doas",
  // 权限修改
  "chmod",
  "chown",
  "chgrp",
  // 文件移动/复制（可能覆盖）
  "mv",
  "cp",
  // 底层磁盘操作
  "dd",
  "mkfs",
  "fdisk",
  "parted",
  "format",
  // 进程控制
  "kill",
  "killall",
  "pkill",
  "taskkill",
  // 系统控制
  "reboot",
  "shutdown",
  "halt",
  "poweroff",
  // 网络操作
  "curl",
  "wget",
  "ssh",
  "scp",
  "rsync",
  // Git 危险操作
  "git push",
  "git reset",
  "git rebase",
  "git checkout",
  "git clean",
  "git stash drop",
]);

/**
 * 检查是否为危险命令
 */
export function isDangerousCommand(command: string): boolean {
  const trimmed = command.toLowerCase().trim();
  for (const dangerous of DANGEROUS_COMMANDS) {
    if (trimmed.startsWith(dangerous)) {
      const after = trimmed.slice(dangerous.length);
      if (after === "" || after.startsWith(" ") || after.startsWith("\t")) {
        return true;
      }
    }
  }
  return false;
}
