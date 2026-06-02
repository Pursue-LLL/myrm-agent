/**
 * CLI Agent 运行器
 *
 * 封装 @anthropic-ai/claude-agent-sdk 的调用，提供统一的接口。
 * 借鉴 Claude-Cowork 的 runner.ts 实现。
 */

import { query, type SDKMessage, type PermissionResult } from "@anthropic-ai/claude-agent-sdk";
import {
  type SessionConfig,
  type PermissionMode,
  type AgentEvent,
  isDangerousCommand,
} from "./types.js";
import { randomUUID } from "crypto";

// ============================================================================
// 会话管理
// ============================================================================

interface ActiveSession {
  id: string;
  config: SessionConfig;
  sdkSessionId?: string;
  abortController: AbortController;
  pendingPermissions: Map<
    string,
    {
      resolve: (result: PermissionResult) => void;
      toolName: string;
      command: string;
    }
  >;
}

const activeSessions = new Map<string, ActiveSession>();

// ============================================================================
// 权限模式管理
// ============================================================================

let currentPermissionMode: PermissionMode = "ask";
const alwaysAllowedCommands = new Set<string>();

export function setPermissionMode(mode: PermissionMode): void {
  currentPermissionMode = mode;
  // 切换模式时清除 always allow 列表
  if (mode === "explore") {
    alwaysAllowedCommands.clear();
  }
}

export function getPermissionMode(): PermissionMode {
  return currentPermissionMode;
}

export function cyclePermissionMode(): PermissionMode {
  const modes: PermissionMode[] = ["explore", "ask", "auto"];
  const currentIndex = modes.indexOf(currentPermissionMode);
  currentPermissionMode = modes[(currentIndex + 1) % modes.length];
  return currentPermissionMode;
}

// ============================================================================
// Agent 检测
// ============================================================================

import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

export async function detectAgents(): Promise<string[]> {
  const available: string[] = [];

  // 检测 Claude Code
  try {
    await execAsync("claude --version");
    available.push("claude-code");
  } catch {
    // Claude Code not installed
  }

  // 检测 Gemini CLI（未来支持）
  // try {
  //   await execAsync("gemini --version");
  //   available.push("gemini-cli");
  // } catch {}

  return available;
}

// ============================================================================
// 会话管理
// ============================================================================

export function createSession(config: SessionConfig): string {
  const sessionId = randomUUID();

  const session: ActiveSession = {
    id: sessionId,
    config,
    abortController: new AbortController(),
    pendingPermissions: new Map(),
  };

  activeSessions.set(sessionId, session);

  // 设置初始权限模式
  if (config.permissionMode) {
    currentPermissionMode = config.permissionMode;
  }

  return sessionId;
}

export function getSession(sessionId: string): ActiveSession | undefined {
  return activeSessions.get(sessionId);
}

export function stopSession(sessionId: string): void {
  const session = activeSessions.get(sessionId);
  if (session) {
    session.abortController.abort();
    // 拒绝所有待处理的权限请求
    for (const [, pending] of session.pendingPermissions) {
      pending.resolve({ behavior: "deny", message: "Session stopped" });
    }
    activeSessions.delete(sessionId);
  }
}

// ============================================================================
// 权限处理
// ============================================================================

export function respondPermission(
  sessionId: string,
  requestId: string,
  allowed: boolean,
  alwaysAllow: boolean
): void {
  const session = activeSessions.get(sessionId);
  if (!session) return;

  const pending = session.pendingPermissions.get(requestId);
  if (!pending) return;

  // 如果选择 always allow，添加到列表
  if (alwaysAllow && allowed) {
    // 提取基础命令
    const baseCommand = pending.command.split(/\s+/)[0];
    if (baseCommand && !isDangerousCommand(baseCommand)) {
      alwaysAllowedCommands.add(baseCommand);
    }
  }

  if (allowed) {
    pending.resolve({ behavior: "allow" });
  } else {
    pending.resolve({ behavior: "deny", message: "User denied permission" });
  }

  session.pendingPermissions.delete(requestId);
}

// ============================================================================
// 消息发送
// ============================================================================

export interface RunOptions {
  sessionId: string;
  prompt: string;
  onEvent: (event: AgentEvent) => void;
}

export async function runAgent(options: RunOptions): Promise<void> {
  const { sessionId, prompt, onEvent } = options;

  const session = activeSessions.get(sessionId);
  if (!session) {
    throw new Error(`Session not found: ${sessionId}`);
  }

  const { config, abortController } = session;

  try {
    const q = query({
      prompt,
      options: {
        cwd: config.cwd,
        resume: config.resumeSessionId || session.sdkSessionId,
        abortController,
        // permissionMode: "bypassPermissions", // 我们自己处理权限
        includePartialMessages: true,
        canUseTool: async (toolName, input, { signal }) => {
          // Explore 模式：阻止所有写操作
          if (currentPermissionMode === "explore") {
            const writeTools = ["write_file", "edit_file", "bash", "shell", "execute"];
            if (writeTools.some((t) => toolName.toLowerCase().includes(t))) {
              return { behavior: "deny", message: "Read-only mode (Explore)" };
            }
          }

          // 提取命令（如果是 bash/shell 工具）
          const command =
            typeof input === "object" && input !== null && "command" in input
              ? String((input as Record<string, unknown>).command)
              : toolName;

          const dangerous = isDangerousCommand(command);

          // Auto 模式：自动批准非危险命令
          if (currentPermissionMode === "auto" && !dangerous) {
            return { behavior: "allow", updatedInput: input };
          }

          // 检查 always allow 列表
          const baseCommand = command.split(/\s+/)[0];
          if (
            alwaysAllowedCommands.has(baseCommand) &&
            !dangerous &&
            currentPermissionMode !== "explore"
          ) {
            return { behavior: "allow", updatedInput: input };
          }

          // 需要用户确认
          const requestId = randomUUID();

          // 发送权限请求事件
          onEvent({
            type: "permission.request",
            sessionId,
            requestId,
            toolName,
            command,
            isDangerous: dangerous,
          });

          // 等待用户响应
          return new Promise<PermissionResult>((resolve) => {
            session.pendingPermissions.set(requestId, {
              resolve,
              toolName,
              command,
            });

            // 处理中止
            signal.addEventListener("abort", () => {
              session.pendingPermissions.delete(requestId);
              resolve({ behavior: "deny", message: "Session aborted" });
            });
          });
        },
      },
    });

    // 流式处理消息
    for await (const message of q) {
      // 捕获 SDK session_id
      if (
        message.type === "system" &&
        "subtype" in message &&
        message.subtype === "init" &&
        "session_id" in message
      ) {
        session.sdkSessionId = message.session_id as string;
      }

      // 转发消息
      onEvent({
        type: "stream.message",
        sessionId,
        message: message as unknown as import("./types.js").SDKMessageLike,
      });

      // 检查结果状态
      if (message.type === "result") {
        const resultMessage = message as { subtype?: string };
        onEvent({
          type: "session.status",
          sessionId,
          status: resultMessage.subtype === "success" ? "completed" : "error",
        });
      }
    }
  } catch (error) {
    if ((error as Error).name === "AbortError") {
      // 会话被中止，不视为错误
      return;
    }
    onEvent({
      type: "session.status",
      sessionId,
      status: "error",
      error: String(error),
    });
  }
}
