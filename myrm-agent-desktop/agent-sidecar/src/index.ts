/**
 * MyrmAgent Agent Sidecar
 *
 * Node.js sidecar 进程，用于与 Claude Agent SDK 交互。
 * 通过 stdin/stdout JSON-RPC 与 Tauri 主进程通信。
 *
 * 架构:
 *   Tauri (Rust) ← JSON-RPC over stdin/stdout → Agent Sidecar (Node.js)
 *                                                     │
 *                                                     └─ @anthropic-ai/claude-agent-sdk
 */

import { query, type SDKMessage, type PermissionResult } from '@anthropic-ai/claude-agent-sdk';
import * as readline from 'readline';

// ============================================================================
// 消息类型定义
// ============================================================================

/** 请求消息类型 */
interface Request {
  id: string;
  method: string;
  params: Record<string, unknown>;
}

/** 响应消息类型 */
interface Response {
  id: string;
  result?: unknown;
  error?: { code: number; message: string };
}

/** 事件消息类型（推送到 Tauri） */
interface Event {
  event: string;
  sessionId: string;
  data: unknown;
}

/** 会话状态 */
interface Session {
  id: string;
  sdkSessionId?: string;
  cwd: string;
  abortController: AbortController;
  pendingPermissions: Map<string, {
    resolve: (result: PermissionResult) => void;
    toolName: string;
    input: unknown;
  }>;
}

// ============================================================================
// 全局状态
// ============================================================================

const sessions = new Map<string, Session>();

// ============================================================================
// JSON-RPC 通信
// ============================================================================

/** 发送 JSON-RPC 响应 */
function sendResponse(response: Response): void {
  process.stdout.write(JSON.stringify(response) + '\n');
}

/** 发送事件到 Tauri */
function sendEvent(event: Event): void {
  process.stdout.write(JSON.stringify(event) + '\n');
}

/** 记录日志（输出到 stderr，不干扰 JSON-RPC） */
function log(message: string): void {
  process.stderr.write(`[agent-sidecar] ${message}\n`);
}

// ============================================================================
// RPC 方法实现
// ============================================================================

/** 检测 Claude Code CLI 是否可用 */
async function detectClaudeCode(): Promise<boolean> {
  try {
    const { execSync } = await import('child_process');
    execSync('claude --version', { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

/** 创建新会话 */
async function createSession(params: { sessionId: string; cwd: string }): Promise<{ success: boolean }> {
  const { sessionId, cwd } = params;

  if (sessions.has(sessionId)) {
    throw new Error(`Session already exists: ${sessionId}`);
  }

  const session: Session = {
    id: sessionId,
    cwd,
    abortController: new AbortController(),
    pendingPermissions: new Map(),
  };

  sessions.set(sessionId, session);
  log(`Session created: ${sessionId}`);

  return { success: true };
}

/** 发送消息到 Claude */
async function sendMessage(params: {
  sessionId: string;
  prompt: string;
  resumeSessionId?: string;
}): Promise<{ success: boolean }> {
  const { sessionId, prompt, resumeSessionId } = params;

  const session = sessions.get(sessionId);
  if (!session) {
    throw new Error(`Session not found: ${sessionId}`);
  }

  // 重置 abort controller
  session.abortController = new AbortController();

  // 在后台启动查询
  (async () => {
    try {
      const q = query({
        prompt,
        options: {
          cwd: session.cwd,
          resume: resumeSessionId || session.sdkSessionId,
          abortController: session.abortController,
          permissionMode: 'default',
          includePartialMessages: true,
          canUseTool: async (toolName, input, { signal }) => {
            // 发送权限请求到 Tauri
            const requestId = crypto.randomUUID();

            sendEvent({
              event: 'permission_request',
              sessionId,
              data: { requestId, toolName, input },
            });

            // 等待用户响应
            return new Promise<PermissionResult>((resolve) => {
              session.pendingPermissions.set(requestId, {
                resolve,
                toolName,
                input,
              });

              // 处理中止
              signal.addEventListener('abort', () => {
                session.pendingPermissions.delete(requestId);
                resolve({ behavior: 'deny', message: 'Session aborted' });
              });
            });
          },
        },
      });

      // 流式接收消息
      for await (const message of q) {
        // 提取 SDK session ID
        if (message.type === 'system' && 'subtype' in message && message.subtype === 'init') {
          const sdkSessionId = (message as { session_id?: string }).session_id;
          if (sdkSessionId) {
            session.sdkSessionId = sdkSessionId;
            sendEvent({
              event: 'session_id_update',
              sessionId,
              data: { sdkSessionId },
            });
          }
        }

        // 转发消息
        sendEvent({
          event: 'message',
          sessionId,
          data: message,
        });

        // 检查完成状态
        if (message.type === 'result') {
          const status = (message as { subtype?: string }).subtype === 'success' ? 'completed' : 'error';
          sendEvent({
            event: 'session_status',
            sessionId,
            data: { status },
          });
        }
      }

      // 正常完成
      sendEvent({
        event: 'done',
        sessionId,
        data: {},
      });
    } catch (error) {
      if ((error as Error).name === 'AbortError') {
        sendEvent({
          event: 'aborted',
          sessionId,
          data: {},
        });
      } else {
        sendEvent({
          event: 'error',
          sessionId,
          data: { message: String(error) },
        });
      }
    }
  })();

  return { success: true };
}

/** 响应权限请求 */
async function respondPermission(params: {
  sessionId: string;
  requestId: string;
  allowed: boolean;
  alwaysAllow?: boolean;
}): Promise<{ success: boolean }> {
  const { sessionId, requestId, allowed, alwaysAllow } = params;

  const session = sessions.get(sessionId);
  if (!session) {
    throw new Error(`Session not found: ${sessionId}`);
  }

  const pending = session.pendingPermissions.get(requestId);
  if (!pending) {
    throw new Error(`Permission request not found: ${requestId}`);
  }

  session.pendingPermissions.delete(requestId);

  if (allowed) {
    pending.resolve({
      behavior: alwaysAllow ? 'allowAndRemember' : 'allow',
      updatedInput: pending.input,
    });
  } else {
    pending.resolve({
      behavior: 'deny',
      message: 'User denied permission',
    });
  }

  return { success: true };
}

/** 停止会话 */
async function stopSession(params: { sessionId: string }): Promise<{ success: boolean }> {
  const { sessionId } = params;

  const session = sessions.get(sessionId);
  if (!session) {
    throw new Error(`Session not found: ${sessionId}`);
  }

  session.abortController.abort();
  sessions.delete(sessionId);

  log(`Session stopped: ${sessionId}`);
  return { success: true };
}

// ============================================================================
// RPC 路由
// ============================================================================

type RpcMethod = (params: Record<string, unknown>) => Promise<unknown>;

const rpcMethods: Record<string, RpcMethod> = {
  detect: detectClaudeCode as RpcMethod,
  createSession: createSession as RpcMethod,
  sendMessage: sendMessage as RpcMethod,
  respondPermission: respondPermission as RpcMethod,
  stopSession: stopSession as RpcMethod,
};

/** 处理 RPC 请求 */
async function handleRequest(request: Request): Promise<void> {
  const { id, method, params } = request;

  const handler = rpcMethods[method];
  if (!handler) {
    sendResponse({
      id,
      error: { code: -32601, message: `Method not found: ${method}` },
    });
    return;
  }

  try {
    const result = await handler(params);
    sendResponse({ id, result });
  } catch (error) {
    sendResponse({
      id,
      error: { code: -32000, message: String(error) },
    });
  }
}

// ============================================================================
// 主程序
// ============================================================================

async function main(): Promise<void> {
  log('Agent sidecar starting...');

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: false,
  });

  rl.on('line', async (line) => {
    try {
      const request = JSON.parse(line) as Request;
      await handleRequest(request);
    } catch (error) {
      log(`Failed to parse request: ${error}`);
    }
  });

  rl.on('close', () => {
    log('Stdin closed, exiting...');
    process.exit(0);
  });

  // 发送就绪信号
  sendEvent({
    event: 'ready',
    sessionId: '',
    data: { version: '0.1.0' },
  });

  log('Agent sidecar ready');
}

main().catch((error) => {
  log(`Fatal error: ${error}`);
  process.exit(1);
});
