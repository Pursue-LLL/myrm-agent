/**
 * [INPUT]
 * @/services/chat::generateChatTitle, updateChatTitle (POS: Chat API client)
 * @/store/useChatStore::useChatStore (POS: sidebar history state)
 *
 * [OUTPUT]
 * autoSaveChat: Auto-generate and save chat titles, then sync the sidebar history.
 *
 * [POS]
 * Title auto-save layer. Reads useChatStore, so it is only imported lazily by the store itself.
 */

import type { ChatHistoryItem, Message } from '@/store/chat/types';
import { generateChatTitle, updateChatTitle } from '@/services/chat';
import { stripUserMessageDisplayText } from '@/lib/utils/messageUtils';
import { disambiguateChatTitle } from '@/lib/utils/titleUtils';
import useConfigStore from '@/store/useConfigStore';
import useChatStore from '@/store/useChatStore';
import { useProjectStore } from '@/store/useProjectStore';
import { consumeMigrationBoundProjectId } from '@/lib/migrationChatHandoff';
import { moveChatToProject } from '@/services/projects';

const CHAT_TITLE_MAX_LENGTH = 50;
const CHAT_SUMMARY_MAX_LENGTH = 100;

/**
 * 自动保存聊天元数据（标题 + 侧边栏）。
 * 消息持久化已由后端 Agent 入口完成，此处只负责标题生成和 UI 同步。
 */
export const autoSaveChat = async (
  chatId: string,
  messages: Message[],
  actionMode: string,
  isIncognito: boolean = false,
): Promise<void> => {
  try {
    if (!messages.length || !chatId) {
      return;
    }

    // Lazy Session Persistence: Do not auto-save titles or add session to sidebar
    // until at least one assistant message exists (avoids phantom blank sessions on early abort).
    const hasAssistantMessage = messages.some((msg) => msg.role === 'assistant');
    if (!hasAssistantMessage) {
      return;
    }

    const title = await _generateTitle(messages);

    await updateChatTitle(chatId, title);

    if (isIncognito) {
      // 阅后即焚模式：禁止将无痕会话添加到前端本地的侧边栏历史列表中，防止 UI 状态泄漏
      return;
    }

    const lastMessage = messages[messages.length - 1]?.content || '';
    const firstUserMessage = messages.find((msg) => msg.role === 'user');
    const firstMessage = firstUserMessage?.content
      ? stripUserMessageDisplayText(firstUserMessage.content).slice(0, CHAT_SUMMARY_MAX_LENGTH)
      : '';

    _updateSidebar(chatId, title, firstMessage, lastMessage, actionMode);
  } catch (error) {
    console.warn(`❌ autoSaveChat failed for ${chatId}:`, error instanceof Error ? error.message : String(error));
  }
};

function _generateTitle(messages: Message[]): Promise<string> {
  const configState = useConfigStore.getState();
  if (configState.enableAutoTitleGeneration && messages.length > 0) {
    return generateChatTitle(messages).catch(() => _fallbackTitle(messages));
  }
  return Promise.resolve(_fallbackTitle(messages));
}

function _fallbackTitle(messages: Message[]): string {
  const firstUserMessage = messages.find((msg) => msg.role === 'user');
  const clean = firstUserMessage?.content ? stripUserMessageDisplayText(firstUserMessage.content) : '';
  return clean
    ? clean.slice(0, CHAT_TITLE_MAX_LENGTH) + (clean.length > CHAT_TITLE_MAX_LENGTH ? '...' : '')
    : 'Untitled Chat';
}

function _updateSidebar(
  chatId: string,
  title: string,
  firstMessage: string,
  lastMessage: string,
  actionMode: string,
): void {
  const { chatHistoryItems, setChatHistoryItems } = useChatStore.getState();
  const summary =
    lastMessage.slice(0, CHAT_SUMMARY_MAX_LENGTH) + (lastMessage.length > CHAT_SUMMARY_MAX_LENGTH ? '...' : '');

  const now = new Date();
  const existing = chatHistoryItems.findIndex((item) => item.id === chatId);

  // 会话标题自动消歧（除当前正在更新的会话之外，若已有同名标题则追加自增序号）
  const otherTitles = chatHistoryItems.filter((item) => item.id !== chatId).map((item) => item.title);
  const resolvedTitle = disambiguateChatTitle(title, otherTitles);

  const resolveProjectIdForSidebar = (): string | null => {
    const boundProjectId = consumeMigrationBoundProjectId();
    if (boundProjectId) {
      return boundProjectId;
    }
    const filter = useProjectStore.getState().activeFilter;
    return typeof filter === 'string' ? filter : null;
  };

  const projectId =
    existing === -1
      ? resolveProjectIdForSidebar()
      : (() => {
          const boundProjectId = consumeMigrationBoundProjectId();
          if (boundProjectId) {
            moveChatToProject(chatId, boundProjectId).catch(() => {});
            return boundProjectId;
          }
          return chatHistoryItems[existing]?.projectId ?? null;
        })();

  const newItem: ChatHistoryItem = {
    id: chatId,
    title: resolvedTitle,
    firstMessage,
    lastMessage: summary,
    actionMode,
    source: 'web',
    projectId,
    updatedAt: now,
    createdAt: now,
  };

  if (existing !== -1) {
    setChatHistoryItems([newItem, ...chatHistoryItems.filter((item) => item.id !== chatId)]);
  } else {
    if (projectId) {
      moveChatToProject(chatId, projectId).catch(() => {});
    }
    setChatHistoryItems([newItem, ...chatHistoryItems]);
  }
}
