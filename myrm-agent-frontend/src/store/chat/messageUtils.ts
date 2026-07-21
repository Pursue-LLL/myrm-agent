import { Message } from '@/store/chat/types';
import useConfigStore from '../useConfigStore';
import { getSuggestions as getSuggestionsService } from '@/services/chat';
import { buildSimpleChatHistory } from './chatHistoryBuilder';

/**
 * 查找指定messageId的assistant消息索引
 */
export const findAssistantMessageIndex = (messages: Message[], messageId: string): number => {
  return messages.findIndex((msg) => msg.messageId === messageId && msg.role === 'assistant');
};

/** Locate a UI artifact by surface_id across assistant messages (newest first). */
export const findUiArtifactLocation = (
  messages: Message[],
  surfaceId: string,
): { messageIndex: number; artifactIndex: number } | null => {
  for (let messageIndex = messages.length - 1; messageIndex >= 0; messageIndex -= 1) {
    const msg = messages[messageIndex];
    if (msg.role !== 'assistant' || !msg.uiArtifacts?.length) {
      continue;
    }
    const artifactIndex = msg.uiArtifacts.findIndex((item) => item.surface_id === surfaceId);
    if (artifactIndex !== -1) {
      return { messageIndex, artifactIndex };
    }
  }
  return null;
};

/**
 * 处理建议生成
 *
 * 搜索模式和 Agent 模式均支持。后端从 DB 读取 filter model 配置。
 */
export const processSuggestions = async (
  lastMsg: Message,
  messages: Message[],
  updateMessage: (messageId: string, suggestions: string[]) => void,
): Promise<void> => {
  const configStore = useConfigStore.getState();
  if (!configStore.generateSearchSuggestions) return;

  if (lastMsg.role === 'assistant' && lastMsg.content.trim().length > 0 && !lastMsg.suggestions) {
    try {
      const chatHistory = buildSimpleChatHistory(messages);
      const suggestions = await getSuggestionsService(chatHistory);
      updateMessage(lastMsg.messageId, suggestions);
    } catch (error) {
      console.error('Failed to get suggestions:', error);
    }
  }
};
