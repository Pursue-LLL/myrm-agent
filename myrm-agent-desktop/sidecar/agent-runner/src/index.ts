/**
 * CLI Agent Runner 入口
 *
 * 通过 stdin/stdout 与 Tauri 进行 JSON-RPC 通信。
 * 设计参考 craft-agents 的 sidecar 通信方式。
 */

import * as readline from "readline";
import {
  detectAgents,
  createSession,
  stopSession,
  runAgent,
  respondPermission,
  setPermissionMode,
  getPermissionMode,
  cyclePermissionMode,
  getSession,
} from "./runner.js";
import type {
  RPCRequest,
  RPCResponse,
  RPCNotification,
  SessionConfig,
  PermissionMode,
  AgentEvent,
} from "./types.js";

// ============================================================================
// JSON-RPC 处理
// ============================================================================

let requestId = 0;

/**
 * 发送响应到 stdout
 */
function sendResponse(id: number, result?: unknown, error?: { code: number; message: string }): void {
  const response: RPCResponse = {
    jsonrpc: "2.0",
    id,
    ...(error ? { error } : { result }),
  };
  console.log(JSON.stringify(response));
}

/**
 * 发送通知到 stdout（无 id，无需响应）
 */
function sendNotification(method: string, params?: Record<string, unknown>): void {
  const notification: RPCNotification = {
    jsonrpc: "2.0",
    method,
    params,
  };
  console.log(JSON.stringify(notification));
}

/**
 * 发送 Agent 事件
 */
function sendAgentEvent(event: AgentEvent): void {
  sendNotification("agent.event", event as unknown as Record<string, unknown>);
}

/**
 * 处理 RPC 请求
 */
async function handleRequest(request: RPCRequest): Promise<void> {
  const { id, method, params = {} } = request;

  try {
    switch (method) {
      // ==================== Agent 检测 ====================
      case "detect_agents": {
        const agents = await detectAgents();
        sendResponse(id, { agents });
        break;
      }

      // ==================== 会话管理 ====================
      case "create_session": {
        const { cwd, permissionMode, resumeSessionId } = params as {
          cwd?: string;
          permissionMode?: PermissionMode;
          resumeSessionId?: string;
        };
        if (!cwd) {
          throw new Error("Missing required field: cwd");
        }
        const sessionId = createSession({
          cwd,
          permissionMode: permissionMode || "ask",
          resumeSessionId,
        });
        sendResponse(id, { sessionId });
        break;
      }

      case "stop_session": {
        const { sessionId } = params as { sessionId: string };
        if (!sessionId) {
          throw new Error("Missing required field: sessionId");
        }
        stopSession(sessionId);
        sendResponse(id, { success: true });
        break;
      }

      // ==================== 消息发送 ====================
      case "send_message": {
        const { sessionId, prompt } = params as { sessionId: string; prompt: string };
        if (!sessionId || !prompt) {
          throw new Error("Missing required fields: sessionId, prompt");
        }

        // 异步运行 Agent，通过事件返回结果
        sendResponse(id, { started: true });

        // 不等待完成，通过事件流返回
        runAgent({
          sessionId,
          prompt,
          onEvent: sendAgentEvent,
        }).catch((error) => {
          sendAgentEvent({
            type: "session.status",
            sessionId,
            status: "error",
            error: String(error),
          });
        });
        break;
      }

      // ==================== 权限管理 ====================
      case "respond_permission": {
        const { sessionId, requestId: reqId, allowed, alwaysAllow } = params as {
          sessionId: string;
          requestId: string;
          allowed: boolean;
          alwaysAllow: boolean;
        };
        if (!sessionId || !reqId || allowed === undefined) {
          throw new Error("Missing required fields: sessionId, requestId, allowed");
        }
        respondPermission(sessionId, reqId, allowed, alwaysAllow || false);
        sendResponse(id, { success: true });
        break;
      }

      case "set_permission_mode": {
        const { mode } = params as { mode: PermissionMode };
        if (!mode) {
          throw new Error("Missing required field: mode");
        }
        setPermissionMode(mode);
        sendResponse(id, { mode: getPermissionMode() });
        break;
      }

      case "get_permission_mode": {
        sendResponse(id, { mode: getPermissionMode() });
        break;
      }

      case "cycle_permission_mode": {
        const newMode = cyclePermissionMode();
        sendResponse(id, { mode: newMode });
        break;
      }

      // ==================== 会话查询 ====================
      case "get_session": {
        const { sessionId } = params as { sessionId: string };
        const session = getSession(sessionId);
        if (session) {
          sendResponse(id, {
            id: session.id,
            config: session.config,
            sdkSessionId: session.sdkSessionId,
          });
        } else {
          sendResponse(id, null);
        }
        break;
      }

      // ==================== 健康检查 ====================
      case "ping": {
        sendResponse(id, { pong: true, timestamp: Date.now() });
        break;
      }

      default:
        sendResponse(id, undefined, {
          code: -32601,
          message: `Method not found: ${method}`,
        });
    }
  } catch (error) {
    sendResponse(id, undefined, {
      code: -32000,
      message: String(error),
    });
  }
}

// ============================================================================
// 主入口
// ============================================================================

function main(): void {
  // 创建 readline 接口
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: false,
  });

  // 发送就绪通知
  sendNotification("ready", { version: "1.0.0" });

  // 处理输入
  rl.on("line", (line) => {
    if (!line.trim()) return;

    try {
      const request = JSON.parse(line) as RPCRequest;

      if (request.jsonrpc !== "2.0") {
        sendResponse(request.id || 0, undefined, {
          code: -32600,
          message: "Invalid JSON-RPC version",
        });
        return;
      }

      handleRequest(request);
    } catch (error) {
      // JSON 解析错误
      sendResponse(0, undefined, {
        code: -32700,
        message: `Parse error: ${error}`,
      });
    }
  });

  // 处理关闭
  rl.on("close", () => {
    process.exit(0);
  });

  // 处理错误
  process.on("uncaughtException", (error) => {
    sendNotification("error", { message: String(error) });
  });

  process.on("unhandledRejection", (reason) => {
    sendNotification("error", { message: String(reason) });
  });
}

main();
