/**
 * CLI Agent 消息适配器
 *
 * 将 CLI Agent (Claude Code) 的消息转换为现有的 Message 类型，
 * 使其可以复用现有的聊天 UI 组件。
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md（如有）
 *
 * [INPUT]
 * - @/store/chat/types::Message, ProgressItem, ToolCallInfo (POS: 聊天消息类型定义)
 * - @/services/cli-agent::AgentMessage (POS: CLI Agent 服务层消息类型)
 *
 * [OUTPUT]
 * - convertCLIMessageToMessage: CLI 消息 → Message 类型转换
 * - createUserMessage: 创建用户消息
 * - createEmptyAssistantMessage: 创建空的助手消息
 * - appendContent: 追加内容到现有消息
 * - appendItem: 追加项目到数组
 * - appendProgressItem: 追加进度步骤
 * - updateProgressItemStatus: 更新进度步骤状态
 * - generateMessageId: 生成消息 ID
 *
 * [POS]
 * CLI Agent 消息适配器。将 Sidecar 返回的 CLI 消息（text、thought、
 * tool_call_start、tool_call_result、permission_request 等）转换为
 * 现有的 Message 类型，使 CLI Agent 可以复用 ProgressSteps、
 * ToolCallApproval 等聊天 UI 组件。是 CLI 可视化工具的核心桥梁。
 */

import type { Message, ProgressItem, ToolCallInfo } from '@/store/chat/types';
import type { AgentMessage } from '@/services/cli-agent';

/**
 * 将 CLI Agent 消息转换为 Message 类型
 */
export function convertCLIMessageToMessage(
  cliMessage: AgentMessage,
  chatId: string,
  existingMessage?: Message,
): Partial<Message> {
  const baseMessage: Partial<Message> = {
    chatId,
    createdAt: existingMessage?.createdAt || new Date(),
    role: 'assistant',
    messageId: existingMessage?.messageId || cliMessage.msgId || generateMessageId(),
  };

  switch (cliMessage.type) {
    case 'text':
      return {
        ...baseMessage,
        content: appendContent(existingMessage?.content, cliMessage.content || ''),
      };

    case 'thought':
      // 思考内容添加到 thinkingItems
      return {
        ...baseMessage,
        content: existingMessage?.content || '',
        thinkingItems: appendItem(existingMessage?.thinkingItems, cliMessage.content || ''),
      };

    case 'tool_call_start': {
      // 工具调用开始 - 添加到 progressSteps
      const progressItem: ProgressItem = {
        step_key: 'tool_call',
        tool_name: cliMessage.toolName || 'Tool',
        reason: formatToolArgs(cliMessage.arguments),
      };

      const result: Partial<Message> = {
        ...baseMessage,
        content: existingMessage?.content || '',
        progressSteps: appendProgressItem(existingMessage?.progressSteps, progressItem),
      };

      // 如果是文件编辑工具，提取 diff 数据到 toolCalls
      const toolName = cliMessage.toolName?.toLowerCase() || '';
      if (isDiffTool(toolName) && cliMessage.arguments) {
        const diff = extractDiff(cliMessage.arguments);
        const filePath = extractFilePath(cliMessage.arguments);
        if (diff) {
          const toolCall: ToolCallInfo = {
            callId: cliMessage.callId || generateMessageId(),
            toolName: cliMessage.toolName || 'edit_file',
            arguments: cliMessage.arguments,
            requiresApproval: false,
            status: 'pending',
            diff,
            filePath,
          };
          result.toolCalls = appendToolCall(existingMessage?.toolCalls, toolCall);
        }
      }

      return result;
    }

    case 'tool_call_result':
      // 工具调用完成 - 更新 progressSteps 状态
      return {
        ...baseMessage,
        content: existingMessage?.content || '',
        progressSteps: updateProgressItemStatus(
          existingMessage?.progressSteps,
          cliMessage.toolName || '',
          cliMessage.status === 'completed' ? 'success' : 'error',
        ),
      };

    case 'permission_request':
      // 权限请求 - 添加到 toolCalls
      if (cliMessage.permissionRequest) {
        const toolCall: ToolCallInfo = {
          callId: cliMessage.permissionRequest.requestId,
          toolName: cliMessage.permissionRequest.toolName,
          arguments: {
            command: cliMessage.permissionRequest.command,
          },
          requiresApproval: true,
          status: 'pending',
        };
        return {
          ...baseMessage,
          content: existingMessage?.content || '',
          toolCalls: appendToolCall(existingMessage?.toolCalls, toolCall),
        };
      }
      return baseMessage;

    case 'session_status':
      // 会话状态变更 - 不修改消息内容
      return baseMessage;

    case 'error':
      // 错误消息
      return {
        ...baseMessage,
        content: `[Warning] Error: ${cliMessage.error || 'Unknown error'}`,
      };

    case 'done':
      // 完成信号 - 不修改消息内容
      return baseMessage;

    default:
      return baseMessage;
  }
}

/**
 * 创建用户消息
 */
export function createUserMessage(content: string, chatId: string): Message {
  return {
    messageId: generateMessageId(),
    chatId,
    createdAt: new Date(),
    content,
    role: 'user',
  };
}

/**
 * 创建空的助手消息（用于开始流式响应）
 */
export function createEmptyAssistantMessage(chatId: string): Message {
  return {
    messageId: generateMessageId(),
    chatId,
    createdAt: new Date(),
    content: '',
    role: 'assistant',
    progressSteps: [],
  };
}

// ============================================================================
// 辅助函数
// ============================================================================

function generateMessageId(): string {
  return `cli-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function appendContent(existing: string | undefined, newContent: string): string {
  return (existing || '') + newContent;
}

function appendItem<T>(existing: T[] | undefined, item: T): T[] {
  return [...(existing || []), item];
}

function appendProgressItem(existing: ProgressItem[] | undefined, item: ProgressItem): ProgressItem[] {
  return [...(existing || []), item];
}

function updateProgressItemStatus(
  existing: ProgressItem[] | undefined,
  toolName: string,
  status: 'success' | 'error',
): ProgressItem[] {
  if (!existing) return [];
  return existing.map((item) => (item.tool_name === toolName ? { ...item, status } : item));
}

function appendToolCall(existing: ToolCallInfo[] | undefined, item: ToolCallInfo): ToolCallInfo[] {
  return [...(existing || []), item];
}

function formatToolArgs(args: Record<string, unknown> | undefined): string {
  if (!args) return '';
  const command = args.command;
  if (typeof command === 'string') {
    return command.length > 100 ? command.slice(0, 100) + '...' : command;
  }
  return JSON.stringify(args).slice(0, 100);
}

/**
 * 检查是否是文件编辑类型的工具（可能包含 diff）
 */
function isDiffTool(toolName: string): boolean {
  const diffTools = ['apply_patch', 'edit_file', 'write_file', 'patch', 'modify_file', 'create_file'];
  return diffTools.some((t) => toolName.includes(t));
}

/**
 * 从工具参数中提取 diff 内容
 */
function extractDiff(args: Record<string, unknown>): string | undefined {
  // 尝试多种可能的字段名
  const diffFields = ['diff', 'patch', 'content', 'changes'];
  for (const field of diffFields) {
    const value = args[field];
    if (typeof value === 'string' && value.includes('@@')) {
      return value;
    }
  }
  return undefined;
}

/**
 * 从工具参数中提取文件路径
 */
function extractFilePath(args: Record<string, unknown>): string | undefined {
  // 尝试多种可能的字段名
  const pathFields = ['file_path', 'filePath', 'path', 'file', 'target'];
  for (const field of pathFields) {
    const value = args[field];
    if (typeof value === 'string') {
      return value;
    }
  }
  return undefined;
}
