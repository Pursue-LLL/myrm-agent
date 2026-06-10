/**
 * [INPUT]
 * @/services/chat::getChatDetail (POS: Chat API client)
 * @/store/useWorkspaceStore::useWorkspaceStore (POS: Workspace state manager)
 *
 * [OUTPUT]
 * initializeChat: Initialize or switch chat sessions with instant snapshot rendering.
 * loadMessages: Fetch chat history from DB.
 * autoSaveChat: Auto-generate and save chat titles.
 *
 * [POS]
 * Chat session lifecycle manager. Handles initialization, DB fetching, and snapshot-first rendering during tab switches.
 */

import crypto from 'crypto';
import { Message, ChatHistoryItem, type ActionMode } from '@/store/chat/types';
import { ChatActionsMethods } from './messageRequest';
import { getChatDetail, getMessages, generateChatTitle, updateChatTitle } from '@/services/chat';
import { ApiError, apiRequest } from '@/lib/api';
import { stripDatetimeTag } from '@/lib/utils/messageUtils';
import useConfigStore from '@/store/useConfigStore';
import useChatStore from '@/store/useChatStore';
import useWorkspaceStore from '@/store/useWorkspaceStore';
import { useProjectStore } from '@/store/useProjectStore';
import { moveChatToProject } from '@/services/projects';
import { abortCurrentUpload } from '@/services/uploadController';

const CHAT_TITLE_MAX_LENGTH = 50;
const CHAT_SUMMARY_MAX_LENGTH = 100;
const VALID_ACTION_MODES: readonly ActionMode[] = ['fast', 'agent', 'deep_research', 'consensus', 'claude_code'];

function normalizeActionMode(actionMode: string | null | undefined): ActionMode {
  if (typeof actionMode === 'string' && VALID_ACTION_MODES.includes(actionMode as ActionMode)) {
    return actionMode as ActionMode;
  }
  return 'agent';
}

/**
 * 加载历史消息（初始加载最新一页）
 */
export const loadMessages = async (chatId: string, actions: ChatActionsMethods): Promise<void> => {
  try {
    actions.setMessages((state) => {
      state.loading = true;
      state.chatId = chatId;
      state.isMessagesLoaded = false;
      state.notFound = false;
      state.loadError = false;
    });

    const chatData = await getChatDetail(chatId, true);
    const page = await getMessages(chatId, { limit: 10, silent: true });

    const messages = parseMessages(page.messages);

    if (messages.length > 0) {
      const firstUserMessage = messages.find((msg) => msg.role === 'user');
      const rawTitle = firstUserMessage?.content || messages[0].content || 'Chat';
      document.title = stripDatetimeTag(rawTitle);
    }

    actions.setMessages((state) => {
      if (state.chatId === chatId) {
        state.messages = messages;
        state.actionMode = normalizeActionMode(chatData.chat.actionMode);
        state.compactedSummary = chatData.chat.compacted_summary;
        state.compactedBeforeId = chatData.chat.compacted_before_id;
        state.workspaceDir = chatData.chat.workspace_dir;
        state.incognitoMode = chatData.chat.is_incognito || false;
        state.hasMoreMessages = page.has_more;
        state.nextCursor = page.next_cursor;
        state.isMessagesLoaded = true;
        state.loading = false;
      }
    });

    apiRequest<{ active: boolean }>(`/chats/${chatId}/sandbox/status`).then((res) => {
      if (res?.active && useChatStore.getState().chatId === chatId) {
        useChatStore.getState().setSandboxMode(true);
      }
    }).catch(() => {});
  } catch (error) {
    console.error('Failed to load chat messages:', error, chatId);

    actions.setMessages((state) => {
      if (state.chatId === chatId) {
        const isNotFound = error instanceof ApiError && (error.code === 40004 || error.code === 404);
        state.notFound = isNotFound;
        state.loadError = !isNotFound; // 非 404 的错误都视为加载错误
        state.isMessagesLoaded = true;
        state.loading = false;
      }
    });
  }
};

/**
 * 加载更早的消息（向上滚动触发）
 */
export const loadOlderMessages = async (actions: ChatActionsMethods): Promise<void> => {
  const state = useChatStore.getState();
  if (!state.chatId || !state.hasMoreMessages || !state.nextCursor || state.loadingOlder) {
    return;
  }

  actions.setMessages((s) => {
    s.loadingOlder = true;
  });

  try {
    const page = await getMessages(state.chatId, {
      before: state.nextCursor,
      limit: 10,
    });

    const olderMessages = parseMessages(page.messages);

    actions.setMessages((s) => {
      if (s.chatId === state.chatId) {
        s.messages = [...olderMessages, ...s.messages];
        s.hasMoreMessages = page.has_more;
        s.nextCursor = page.next_cursor;
        s.loadingOlder = false;
      }
    });
  } catch (error) {
    console.error('Failed to load older messages:', error);
    actions.setMessages((s) => {
      s.loadingOlder = false;
    });
  }
};

function parseMessages(raw: Message[]): Message[] {
  return raw.map((msg) => ({
    ...msg,
    ...(typeof (msg as Record<string, unknown>).metadata === 'string'
      ? JSON.parse((msg as Record<string, unknown>).metadata as string)
      : (msg as Record<string, unknown>).metadata),
  }));
}

/**
 * 初始化聊天
 */
export const initializeChat = (
  id: string | undefined,
  state: { messages: Message[]; chatId?: string },
  actions: ChatActionsMethods,
): void => {
  // 如果没有ID，重置为新聊天状态
  if (!id) {
    abortCurrentUpload();
    actions.setMessages((state) => {
      state.messages = [];
      state.newChatCreated = true;
      state.isMessagesLoaded = true;
      state.notFound = false;
      state.loadError = false;
      state.loading = false;
      state.messageAppeared = false;
      state.compactedSummary = null;
      state.compactedBeforeId = null;
      state.workspaceDir = null;
      state.incognitoMode = false;
      state.sandboxMode = false;
      const timestamp = Date.now().toString(36);
      const microTime = (performance.now() * 1000).toString(36).replace('.', '');
      const randomBytes = crypto.randomBytes(8).toString('hex');
      const counter = ((Math.random() * 0xffff) | 0).toString(36);
      state.chatId = `c-${timestamp}-${microTime}-${randomBytes}-${counter}`;
    });
    actions.clearCurrentSessionMessageId();
  }
  // 如果有ID且与当前chatId不同，加载聊天
  else if (state.chatId !== id) {
    abortCurrentUpload();
    
    // Check if we have a snapshot in WorkspaceStore
    const pane = useWorkspaceStore.getState().panes.find((p: any) => p.chatId === id);
    
    if (pane && pane.snapshot) {
      // Instant rendering from snapshot
      actions.setMessages((state) => {
        Object.assign(state, pane.snapshot);
        state.chatId = id;
        state.isMessagesLoaded = true;
      });
      actions.clearCurrentSessionMessageId();
      // Still call loadMessages in background to ensure we're fully up-to-date
      // but without showing loading state
      const silentActions = {
        ...actions,
        setMessages: (updater: (state: any) => void) => {
          actions.setMessages((state) => {
            // Only apply updates if we're still on the same chat
            if (state.chatId === id) {
              const draft = { ...state };
              updater(draft);
              // Don't override loading state since we already rendered snapshot
              draft.loading = state.loading;
              Object.assign(state, draft);
            }
          });
        }
      };
      const snapshot = useWorkspaceStore.getState().panes[id]?.snapshot;
    if (snapshot?.loading) {
      console.log(`[messageManagement] Skip loadMessages for ${id} because snapshot is loading`);
      return;
    }

    loadMessages(id, silentActions).catch(console.error);
    } else {
      // 立即重置状态，确保不显示之前的聊天内容
      actions.setMessages((state) => {
        state.messages = [];
        state.isMessagesLoaded = false;
        state.notFound = false;
        state.loadError = false;
        state.loading = true;
        state.messageAppeared = false;
        state.compactedSummary = null;
        state.compactedBeforeId = null;
        state.workspaceDir = null;
        state.incognitoMode = false;
        state.sandboxMode = false;
        state.chatId = id;
      });
      actions.clearCurrentSessionMessageId();
      loadMessages(id, actions);
    }
  }
};

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

    const title = await _generateTitle(messages);

    await updateChatTitle(chatId, title);

    if (isIncognito) {
      // 阅后即焚模式：禁止将无痕会话添加到前端本地的侧边栏历史列表中，防止 UI 状态泄漏
      return;
    }

    const lastMessage = messages[messages.length - 1]?.content || '';
    const firstUserMessage = messages.find((msg) => msg.role === 'user');
    const firstMessage = firstUserMessage?.content
      ? stripDatetimeTag(firstUserMessage.content).slice(0, CHAT_SUMMARY_MAX_LENGTH)
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
  const clean = firstUserMessage?.content ? stripDatetimeTag(firstUserMessage.content) : '';
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

  const projectId =
    existing === -1
      ? (() => {
          const filter = useProjectStore.getState().activeFilter;
          return typeof filter === 'string' ? filter : null;
        })()
      : (chatHistoryItems[existing]?.projectId ?? null);

  const newItem: ChatHistoryItem = {
    id: chatId,
    title,
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
