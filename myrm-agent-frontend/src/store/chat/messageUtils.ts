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

/**
 * 移除某条消息上的 waiting_for_turn 进度步骤。
 *
 * 用户在前端取消请求时，后端 pump 可能在取得项目锁之前就退出了，
 * 不会再发出 waiting_for_turn_clear SSE；本地残留的等待步骤在此清除。
 * 返回新数组（immutable），无匹配时原样返回。
 */
export const removeWaitingForTurnStep = (
  messages: Message[],
  messageId: string,
): Message[] => {
  const next = messages.map((msg) => {
    if (msg.messageId !== messageId || !msg.progressSteps?.length) return msg;
    const hasWaitingStep = msg.progressSteps.some((step) => step.step_key === 'waiting_for_turn');
    if (!hasWaitingStep) return msg;
    return {
      ...msg,
      progressSteps: msg.progressSteps.filter((step) => step.step_key !== 'waiting_for_turn'),
    };
  });
  const changed = next.some((msg, index) => msg !== messages[index]);
  return changed ? next : messages;
};

/**
 * Ensure an assistant placeholder exists for stream events that may arrive before MESSAGE.
 * Returns the message index, or -1 when messageId is missing.
 */
export const ensureAssistantStreamMessage = (
  messages: Message[],
  messageId: string | undefined,
  chatIdFallback: string,
): number => {
  const normalizedId = messageId?.trim();
  if (!normalizedId) {
    return -1;
  }
  const existing = findAssistantMessageIndex(messages, normalizedId);
  if (existing !== -1) {
    return existing;
  }
  messages.push({
    content: '',
    messageId: normalizedId,
    chatId: chatIdFallback,
    role: 'assistant',
    progressSteps: [],
    createdAt: new Date(),
  });
  return messages.length - 1;
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
