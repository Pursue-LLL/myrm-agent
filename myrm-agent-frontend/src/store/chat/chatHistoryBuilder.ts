import { Message } from './types';

/**
 * 构建简化 chat_history（纯文本），用于 suggestions 等轻量场景。
 *
 * 完整的 chat_history 构建已迁移到后端（从 DB 加载），
 * 前端不再负责构建 Agent 所需的聊天历史。
 */
export const buildSimpleChatHistory = (messages: Message[]): [string, string][] => {
  return messages.map((msg) => [msg.role === 'user' ? 'human' : 'assistant', msg.content]);
};
