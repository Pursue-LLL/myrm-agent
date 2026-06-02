/**
 * CLI Agent 消息处理器
 *
 * 处理 Claude Code 等 CLI Agent 的消息发送和响应。
 * 将 Tauri IPC 调用集成到现有的聊天架构中。
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md（如有）
 *
 * [INPUT]
 * - @/store/chat/types::Message, ActionMode, AgentConfig (POS: 聊天消息和配置类型)
 * - @/services/cli-agent::sendAgentMessage, listenAgentMessages, listenAgentPermission,
 *   listenAgentStatus, createAgentSession (POS: CLI Agent Tauri IPC 服务)
 * - @/lib/utils/cliAgentAdapter::convertCLIMessageToMessage, createUserMessage,
 *   createEmptyAssistantMessage (POS: CLI 消息适配器)
 * - @/store/useCLIAgentStore::useCLIAgentStore (POS: CLI Agent 状态管理)
 *
 * [OUTPUT]
 * - isCLIAgentMode(actionMode): 检测是否为 CLI Agent 模式
 * - sendCLIAgentMessage(input, state, actions): 发送 CLI Agent 消息
 *   - 从 agentConfig 获取 agentId、工作目录、权限模式
 *   - 创建/复用 CLI 会话
 *   - 添加用户消息到聊天
 *   - 监听 CLI 响应（消息、权限、状态）
 *   - 转换消息格式并更新 UI
 *
 * [POS]
 * CLI Agent 消息处理器。负责发送消息到 CLI Agent（通过 Tauri IPC）
 * 并监听流式响应。将 CLI 消息转换为 Message 类型，更新到聊天状态。
 * 是 CLI 可视化工具的核心入口，连接前端 UI 和 Rust/Node.js 后端。
 */

import type { Message, ActionMode, AgentConfig } from '@/store/chat/types';
import {
  sendAgentMessage,
  listenAgentMessages,
  listenAgentPermission,
  listenAgentStatus,
  createAgentSession,
  type AgentMessage,
} from '@/services/cli-agent';
import {
  convertCLIMessageToMessage,
  createUserMessage,
  createEmptyAssistantMessage,
} from '@/lib/utils/cliAgentAdapter';
import { useCLIAgentStore } from '@/store/useCLIAgentStore';

// ============================================================================
// 类型定义
// ============================================================================

export interface CLIAgentState {
  messages: Message[];
  chatId: string | undefined;
  loading: boolean;
  messageAppeared: boolean;
  agentConfig: AgentConfig | null;
}

export interface CLIAgentActions {
  setMessages: (updater: (state: { messages: Message[] }) => void) => void;
  setLoading: (loading: boolean) => void;
  setMessageAppeared: (appeared: boolean) => void;
  scheduleAutoSave: () => void;
  setInputMessage: (message: string) => void;
}

// 当前 CLI 会话 ID（在应用生命周期内保持）
let currentCLISessionId: string | null = null;

// ============================================================================
// CLI Agent 检测
// ============================================================================

/**
 * 检测当前是否为 CLI Agent 模式
 */
export function isCLIAgentMode(actionMode: ActionMode): boolean {
  return actionMode === 'claude_code';
}

// ============================================================================
// 会话管理
// ============================================================================

/**
 * 从 agentConfig 解析工作目录
 */
function getWorkingDirectory(agentConfig: AgentConfig | null): string {
  if (agentConfig?.agentDescription?.startsWith('workingDirectory:')) {
    return agentConfig.agentDescription.replace('workingDirectory:', '');
  }
  return '/';
}

/**
 * 从 agentConfig 获取 CLI Agent ID
 */
function getAgentId(agentConfig: AgentConfig | null): string {
  // 支持的 CLI Agent: claude-code, codex, gemini
  const validAgentIds = ['claude-code', 'codex', 'gemini'];
  if (agentConfig?.presetId && validAgentIds.includes(agentConfig.presetId)) {
    return agentConfig.presetId;
  }
  return 'claude-code'; // 默认使用 Claude Code
}

/**
 * 确保 CLI 会话存在
 */
async function ensureCLISession(agentConfig: AgentConfig | null): Promise<string> {
  if (currentCLISessionId) {
    return currentCLISessionId;
  }

  // 检测是否在 Tauri 环境
  if (typeof window === 'undefined' || !('__TAURI_INTERNALS__' in window)) {
    throw new Error('CLI Agent requires Tauri environment');
  }

  // 获取 Agent ID、工作目录和权限模式
  const agentId = getAgentId(agentConfig);
  const cwd = getWorkingDirectory(agentConfig);
  const permissionMode = useCLIAgentStore.getState().permissionMode;

  // 创建新会话
  const session = await createAgentSession(agentId, cwd, permissionMode);
  currentCLISessionId = session.id;

  // 设置工作目录到 CLI Agent Store（用于侧边栏工作区树）
  if (cwd) {
    useCLIAgentStore.getState().setWorkingDirectory(cwd);
  }

  return session.id;
}

// ============================================================================
// 消息处理
// ============================================================================

/**
 * 发送 CLI Agent 消息
 */
export async function sendCLIAgentMessage(
  input: string,
  state: CLIAgentState,
  actions: CLIAgentActions,
): Promise<void> {
  const chatId = state.chatId || 'cli-chat';

  try {
    // 确保会话存在
    const sessionId = await ensureCLISession(state.agentConfig);

    // 添加用户消息
    const userMessage = createUserMessage(input, chatId);
    actions.setMessages((s) => {
      s.messages = [...s.messages, userMessage];
    });

    // 清空输入框
    actions.setInputMessage('');

    // 创建空的助手消息
    const assistantMessage = createEmptyAssistantMessage(chatId);
    actions.setMessages((s) => {
      s.messages = [...s.messages, assistantMessage];
    });

    // 设置消息监听
    const _unlistenMessage = await listenAgentMessages(sessionId, (msg) => {
      actions.setMessageAppeared(true);
      actions.setMessages((s) => {
        const lastIndex = s.messages.length - 1;
        if (lastIndex >= 0 && s.messages[lastIndex].role === 'assistant') {
          const updated = convertCLIMessageToMessage(msg, chatId, s.messages[lastIndex]);
          s.messages[lastIndex] = { ...s.messages[lastIndex], ...updated };
        }
      });

      // 检查是否完成
      if (msg.type === 'done' || msg.type === 'error') {
        actions.setLoading(false);
        actions.scheduleAutoSave();
      }
    });

    // 设置权限请求监听
    const _unlistenPermission = await listenAgentPermission(sessionId, (req) => {
      actions.setMessages((s) => {
        const lastIndex = s.messages.length - 1;
        if (lastIndex >= 0 && s.messages[lastIndex].role === 'assistant') {
          const permissionMessage: AgentMessage = {
            type: 'permission_request',
            permissionRequest: req,
          };
          const updated = convertCLIMessageToMessage(permissionMessage, chatId, s.messages[lastIndex]);
          s.messages[lastIndex] = { ...s.messages[lastIndex], ...updated };
        }
      });
    });

    // 设置状态监听
    const _unlistenStatus = await listenAgentStatus(sessionId, (status, error) => {
      if (status === 'completed' || status === 'error') {
        actions.setLoading(false);
        actions.scheduleAutoSave();
      }
      if (error) {
        actions.setMessages((s) => {
          const lastIndex = s.messages.length - 1;
          if (lastIndex >= 0 && s.messages[lastIndex].role === 'assistant') {
            s.messages[lastIndex].content += `\n\n[Warning] Error: ${error}`;
          }
        });
      }
    });

    // 发送消息
    await sendAgentMessage(sessionId, input);

    // 消息发送成功，等待流式响应
    // 监听器会在消息完成时清理
  } catch (error) {
    actions.setLoading(false);

    // 添加错误消息
    actions.setMessages((s) => {
      const lastIndex = s.messages.length - 1;
      if (lastIndex >= 0 && s.messages[lastIndex].role === 'assistant') {
        s.messages[lastIndex].content = `[Warning] CLI Agent Error: ${error}`;
      }
    });
  }
}
