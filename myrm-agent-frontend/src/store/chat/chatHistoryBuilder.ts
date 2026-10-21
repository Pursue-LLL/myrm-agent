import { Message } from './types';

/**
 * 构建简化 chat_history（纯文本），用于 suggestions 等轻量场景。
 * Agent 完整历史由后端从 DB 加载；本函数仅服务轻量前端调用。
 */
export const buildSimpleChatHistory = (messages: Message[]): [string, string][] => {
  return messages.map((msg) => [msg.role === 'user' ? 'human' : 'assistant', msg.content]);
};
