/**
 * [INPUT]
 * @/services/chat::getChatDetail (POS: Chat API client)
 * @/store/useWorkspaceStore::useWorkspaceStore (POS: Workspace state manager)
 * @/lib/utils/agentConfigMapper::buildAgentConfig (POS: Agent→AgentConfig 标准映射)
 *
 * [OUTPUT]
 * initializeChat: Initialize or switch chat sessions with instant snapshot rendering.
 * resolveInstantChatSnapshot: Resolve workspace pane or LRU snapshot for a chat id.
 * loadMessages: Fetch chat history from DB + restore bound agentConfig (optional instant-session preserve).
 * autoSaveChat: Auto-generate and save chat titles.
 *
 * [POS]
 * Chat session lifecycle manager. Handles initialization, DB fetching, and snapshot-first rendering during tab switches.
 */

import crypto from 'crypto';
import { Message, ChatHistoryItem, type ActionMode, type ChatState } from '@/store/chat/types';
import { ChatActionsMethods } from './messageRequest';
import {
  getChatDetail,
  getMessages,
  generateChatTitle,
  updateChatTitle,
  getContextPins,
  listContextBranches,
} from '@/services/chat';
import { ApiError, apiRequest } from '@/lib/api';
import { stripUserMessageDisplayText } from '@/lib/utils/messageUtils';
import { disambiguateChatTitle } from '@/lib/utils/titleUtils';
import { buildAgentConfig } from '@/lib/utils/agentConfigMapper';
import useConfigStore from '@/store/useConfigStore';
import useChatStore from '@/store/useChatStore';
import { normalizeHydratedClarification } from '@/store/chat/clarificationState';
import { normalizeHydratedDirectoryRequest } from '@/store/chat/directoryRequestState';
import { normalizeSessionAccessRoots } from '@/store/chat/types/sessionAccess';
import { resolveMessageCreatedAtMs } from '@/components/features/message-box/memoryLifecyclePhases';
import useAgentStore from '@/store/useAgentStore';
import { useSkillStore } from '@/store/skill';
import useWorkspaceStore from '@/store/useWorkspaceStore';
import {
  extractNavigationSnapshot,
  getChatNavigationSnapshot,
  saveChatNavigationSnapshot,
} from '@/store/chat/chatNavigationSnapshotCache';
import { resolveHydratedMoaPresetId, writeStoredMoaPresetId } from '@/store/chat/moaPresetStorage';
import { normalizeSecurityPreset } from '@/store/chat/securityPreset';
import { mergeChatSessionConfig } from '@/store/chat/chatSessionConfig';
import { useProjectStore } from '@/store/useProjectStore';
import { consumeMigrationBoundProjectId } from '@/lib/migrationChatHandoff';
import { moveChatToProject } from '@/services/projects';
import { abortCurrentUpload } from '@/services/uploadController';

const CHAT_TITLE_MAX_LENGTH = 50;
const CHAT_SUMMARY_MAX_LENGTH = 100;
const VALID_ACTION_MODES: readonly ActionMode[] = ['fast', 'agent', 'deep_research', 'claude_code'];

export interface LoadMessagesOptions {
  preserveInstantSessionConfig?: boolean;
  /** 内部使用：attach 404 后重拉最新消息时跳过再次 attach，防止恢复循环。 */
  skipActiveTurnAttach?: boolean;
}

function normalizeActionMode(actionMode: string | null | undefined): ActionMode {
  if (typeof actionMode === 'string' && VALID_ACTION_MODES.includes(actionMode as ActionMode)) {
    return actionMode as ActionMode;
  }
  return 'agent';
}

/**
 * Restore agentConfig when loading a historical chat that was bound to a specific agent.
 * Runs asynchronously to avoid blocking message rendering.
 */
function restoreAgentConfigFromChat(chatId: string, agentId: string | null | undefined): void {
  if (!agentId) {
    return;
  }

  const currentConfig = useChatStore.getState().agentConfig;
  if (currentConfig?.agentId === agentId) {
    return;
  }

  useAgentStore
    .getState()
    .fetchAgent(agentId)
    .then(async (agent) => {
      if (!agent || useChatStore.getState().chatId !== chatId) {
        return;
      }
      const { fetchMarketSkills, fetchLocalSkills } = useSkillStore.getState();
      await Promise.all([fetchMarketSkills(true), fetchLocalSkills()]);
      useChatStore.getState().setAgentConfig(buildAgentConfig(agent));
    })
    .catch(() => {});
}

/**
 * 加载历史消息（初始加载最新一页）
 */
export const loadMessages = async (
  chatId: string,
  actions: ChatActionsMethods,
  options?: LoadMessagesOptions,
): Promise<void> => {
  if (typeof window !== 'undefined' && (window as any).__MYRM_LOADMSGS_CLOCK__ !== undefined) {
    try {
      const cutoff = (window as any).__MYRM_LOADMSGS_CLOCK__;
      // Diagnostic probe (temp): log any loadMessages within the clock window —
      // mid-stream or not — so a stale reload that drops store-injected state
      // (routingTier) always leaves a caller stack.
      const st = useChatStore.getState();
      if (Date.now() < cutoff) {
        console.warn('[MYRM_LOADMSGS] loadMessages fired!', {
          chatId,
          loading: st.loading,
          currentSessionMessageId: st.currentSessionMessageId,
          msgCount: (st.messages ?? []).length,
        });
        console.warn('[MYRM_LOADMSGS] stack:', new Error('loadMessages caller').stack);
      }
    } catch {
      /* diagnostic only */
    }
  }
  const preserveInstantSessionConfig = options?.preserveInstantSessionConfig ?? false;
  // Snapshot whether a live turn was streaming when this load started. If so,
  // the DB snapshot may not have persisted the in-flight assistant message
  // (SSE-injected routingTier etc.), so we merge instead of replacing below.
  const activeStreamAtStart = useChatStore.getState().currentSessionMessageId ?? null;
  try {
    actions.setMessages((state) => {
      state.loading = true;
      state.chatId = chatId;
      if (!preserveInstantSessionConfig) {
        state.isMessagesLoaded = false;
      }
      state.notFound = false;
      state.loadError = false;
    });

    // Retry transient API failures (e.g. backend restart under parallel E2E).
    // Without this, one failed fetch left isMessagesLoaded=true with an empty
    // list and never retried, stranding the UI on a skeleton until reload.
    let chatData: Awaited<ReturnType<typeof getChatDetail>> | null = null;
    let page: Awaited<ReturnType<typeof getMessages>> | null = null;
    let lastFetchError: unknown;
    const maxFetchAttempts = 3;
    for (let attempt = 1; attempt <= maxFetchAttempts; attempt++) {
      try {
        [chatData, page] = await Promise.all([
          getChatDetail(chatId, true),
          getMessages(chatId, { limit: 10, silent: true }),
        ]);
        break;
      } catch (error) {
        lastFetchError = error;
        if (attempt < maxFetchAttempts) {
          await new Promise((resolve) => setTimeout(resolve, 500 * attempt));
        }
      }
    }
    if (!chatData || !page) {
      throw lastFetchError;
    }

    const messages = parseMessages(page.messages);

    if (messages.length > 0) {
      const firstUserMessage = messages.find((msg) => msg.role === 'user');
      const rawTitle = firstUserMessage?.content || messages[0].content || 'Chat';
      document.title = stripUserMessageDisplayText(rawTitle);
    }

    actions.setMessages((state) => {
      if (state.chatId === chatId) {
        if (activeStreamAtStart) {
          // A live turn was streaming when this load started: the DB snapshot
          // may still lack the in-flight assistant message. Keep any local
          // assistant that is absent from the DB (or merge its store-injected
          // fields over the DB row) so routingTier / modelTier are never lost
          // by a stale refresh.
          const dbById = new Map(messages.map((m) => [m.messageId, m]));
          const merged = messages.map((dbMsg) => {
            if (dbMsg.role === 'assistant') {
              const local = state.messages.find((m) => m.messageId === dbMsg.messageId);
              if (local) {
                return { ...dbMsg, ...local };
              }
            }
            return dbMsg;
          });
          for (const local of state.messages) {
            if (
              !dbById.has(local.messageId) &&
              local.role === 'assistant' &&
              (local.routingTier !== undefined || local.modelTier !== undefined)
            ) {
              merged.push(local);
            }
          }
          state.messages = merged;
        } else {
          state.messages = messages;
        }
        const isIncognito = chatData.chat.is_incognito || false;
        state.incognitoMode = isIncognito;
        if (!preserveInstantSessionConfig) {
          state.actionMode = normalizeActionMode(chatData.chat.actionMode);
        }
        state.activeMoaPresetId = resolveHydratedMoaPresetId(
          chatId,
          {
            actionMode: state.actionMode,
            incognitoMode: isIncognito,
          },
          chatData.chat.activeMoaPresetId ?? null,
        );
        if (!isIncognito && state.activeMoaPresetId) {
          writeStoredMoaPresetId(chatId, state.activeMoaPresetId);
        }
        state.compactedSummary = chatData.chat.compacted_summary;
        state.compactedBeforeId = chatData.chat.compacted_before_id;
        state.lastCompactionMeta = null;
        state.workspaceDir = chatData.chat.workspace_dir;
        state.sessionSkillOverrides = chatData.chat.session_loaded_skill_names;
        state.sessionAccessRoots = normalizeSessionAccessRoots(chatData.chat.session_access_roots);
        state.hasMoreMessages = page.has_more;
        state.nextCursor = page.next_cursor;
        state.isMessagesLoaded = true;
        state.loading = false;
      }
    });

    if (!preserveInstantSessionConfig) {
      restoreAgentConfigFromChat(chatId, chatData.chat.agent_id);
    }

    if (!preserveInstantSessionConfig && !options?.skipActiveTurnAttach) {
      console.log('[MYRM-ATTACH] loadMessages triggers maybeAttachToActiveTurn', {
        chatId,
        preserveInstantSessionConfig,
        skip: options?.skipActiveTurnAttach,
      });
      void maybeAttachToActiveTurn(chatId, actions);
    } else {
      console.log('[MYRM-ATTACH] loadMessages SKIPS attach', {
        chatId,
        preserveInstantSessionConfig,
        skip: options?.skipActiveTurnAttach,
      });
    }

    apiRequest<{ active: boolean }>(`/chats/${chatId}/sandbox/status`)
      .then((res) => {
        if (res?.active && useChatStore.getState().chatId === chatId) {
          useChatStore.getState().setSandboxMode(true);
        }
      })
      .catch(() => {});

    void getContextPins(chatId)
      .then(({ files }) => {
        if (useChatStore.getState().chatId === chatId) {
          useChatStore.getState().setContextPinnedFiles(files);
        }
      })
      .catch(() => {
        if (useChatStore.getState().chatId === chatId) {
          useChatStore.getState().setContextPinnedFilesLoadError('load_failed');
        }
      });

    if (chatData.chat.compacted_summary) {
      void listContextBranches(chatId)
        .then((branches) => {
          if (useChatStore.getState().chatId === chatId) {
            useChatStore.getState().setContextBranches(branches);
          }
        })
        .catch(() => {
          if (useChatStore.getState().chatId === chatId) {
            useChatStore.getState().setContextBranchesLoadError('load_failed');
          }
        });
    } else {
      useChatStore.getState().setContextBranches([]);
      useChatStore.getState().setContextBranchesLoadError(null);
    }
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

/** 正在尝试恢复进行中 agent 执行的 chat，防止并发重复 attach。 */
const activeTurnAttachInFlight = new Set<string>();

/**
 * 页面重载 / 重新进入 chat 后，若最后一条是 user 消息且无 assistant 回复，
 * agent 可能仍在后端执行。尝试 attachToChat 恢复 SSE 流；
 * attach 404（任务已结束）时重新拉取最终消息，避免 UI 卡在"已发送未回复"。
 */
async function maybeAttachToActiveTurn(chatId: string, actions: ChatActionsMethods): Promise<void> {
  if (activeTurnAttachInFlight.has(chatId)) {
    return;
  }

  const state = useChatStore.getState();
  console.log('[MYRM-ATTACH] maybeAttachToActiveTurn guard check', {
    chatId,
    stateChatId: state.chatId,
    loading: state.loading,
    hasAbort: Boolean(state.abortController),
    msgCount: (state.messages ?? []).length,
    lastRole: (state.messages ?? [])[(state.messages ?? []).length - 1]?.role,
  });
  if (state.chatId !== chatId || state.loading || state.abortController) {
    return;
  }

  const messages = state.messages ?? [];
  const last = messages[messages.length - 1];
  if (!last || last.role !== 'user') {
    return;
  }

  activeTurnAttachInFlight.add(chatId);
  try {
    console.log('[MYRM-ATTACH] calling attachToChat', chatId);
    const { attachToChat } = await import('./messageRequest');
    const attached = await attachToChat(chatId, actions, useChatStore.getState);
    console.log('[MYRM-ATTACH] attachToChat done', { chatId, attached });
    if (!attached) {
      // Agent finished before we could attach — refetch final messages.
      await loadMessages(chatId, actions, { skipActiveTurnAttach: true });
    }
  } catch (error) {
    console.warn('Failed to resume active agent turn:', error);
  } finally {
    activeTurnAttachInFlight.delete(chatId);
  }
}

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
  return raw.map((msg) => {
    const rawRecord = msg as Record<string, unknown>;
    const metadata =
      typeof rawRecord.metadata === 'string'
        ? (JSON.parse(rawRecord.metadata) as Record<string, unknown>)
        : ((rawRecord.metadata as Record<string, unknown> | undefined) ?? {});

    const citedMemoryIds = normalizeStringArray(metadata.citedMemoryIds ?? rawRecord.citedMemoryIds);
    const citedMemoryRefs = normalizeCitedMemoryRefs(metadata.citedMemoryRefs ?? rawRecord.citedMemoryRefs);

    const createdAtMs = resolveMessageCreatedAtMs(
      (msg.createdAt ?? rawRecord.created_at ?? rawRecord.createdAt) as Date | string | number | undefined,
    );

    const parsed = {
      ...msg,
      ...metadata,
      createdAt: createdAtMs != null ? new Date(createdAtMs) : new Date(),
      ...(citedMemoryIds ? { citedMemoryIds } : {}),
      ...(citedMemoryRefs ? { citedMemoryRefs } : {}),
    } as Message;

    const persistedRequestMessageId = metadata.request_message_id;
    if (typeof persistedRequestMessageId === 'string' && persistedRequestMessageId.length > 0) {
      parsed.requestMessageId = persistedRequestMessageId;
    }

    if (parsed.clarification) {
      parsed.clarification = normalizeHydratedClarification(parsed.clarification);
    }

    if (parsed.directoryRequest) {
      parsed.directoryRequest = normalizeHydratedDirectoryRequest(parsed.directoryRequest);
    }

    if (!parsed.reasoning) {
      const persistedReasoning = metadata.reasoning_content;
      if (typeof persistedReasoning === 'string' && persistedReasoning.trim().length > 0) {
        parsed.reasoning = persistedReasoning;
      }
    }

    const rawBudget = metadata.contextBudget ?? metadata.context_budget;
    if (rawBudget && typeof rawBudget === 'object' && !parsed.contextBudget) {
      parsed.contextBudget = rawBudget as Message['contextBudget'];
    }

    return parsed;
  });
}

function normalizeStringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  const ids = value.filter((item): item is string => typeof item === 'string' && item.length > 0);
  return ids.length > 0 ? ids : undefined;
}

function normalizeCitedMemoryRefs(value: unknown): Message['citedMemoryRefs'] {
  if (!Array.isArray(value)) {
    return undefined;
  }
  const refs = value.filter(
    (item): item is NonNullable<Message['citedMemoryRefs']>[number] =>
      typeof item === 'object' && item !== null && typeof (item as { id?: unknown }).id === 'string',
  );
  return refs.length > 0 ? refs : undefined;
}

export interface InitializeChatOptions {
  /** Re-fetch messages even when `state.chatId` already matches (E2E attach / error recovery). */
  forceReload?: boolean;
}

/**
 * 初始化聊天
 */
export const initializeChat = (
  id: string | undefined,
  state: { messages: Message[]; chatId?: string; loading?: boolean; currentSessionMessageId?: string | null },
  actions: ChatActionsMethods,
  options?: InitializeChatOptions,
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
      state.contextBranches = [];
      state.contextPinnedFiles = [];
      state.contextBranchesLoadError = null;
      state.contextPinnedFilesLoadError = null;
      state.lastCompactionMeta = null;
      state.workspaceDir = null;
      state.incognitoMode = false;
      state.sandboxMode = false;
      state.activeMoaPresetId = null;
      state.securityPreset = normalizeSecurityPreset(state.agentConfig?.defaultSecurityPreset);
      const timestamp = Date.now().toString(36);
      const microTime = (performance.now() * 1000).toString(36).replace('.', '');
      const randomBytes = crypto.randomBytes(8).toString('hex');
      const counter = ((Math.random() * 0xffff) | 0).toString(36);
      state.chatId = `c-${timestamp}-${microTime}-${randomBytes}-${counter}`;
    });
    actions.clearCurrentSessionMessageId();
  }
  // 如果有ID且与当前chatId不同，或强制刷新，加载聊天
  else if (state.chatId !== id || options?.forceReload) {
    abortCurrentUpload();

    if (options?.forceReload && state.chatId === id) {
      // A live turn (loading && currentSessionMessageId) is streaming
      // store-injected state such as routingTier; forceReload would clear the
      // store and rebuild from a DB snapshot that has not persisted the
      // assistant message yet, silently dropping the tier. Refuse the reload
      // while an active turn is in flight — the stream finalizes the store.
      if (state.loading === true && state.currentSessionMessageId) {
        return;
      }
      actions.setMessages((draft) => {
        draft.messages = [];
        draft.isMessagesLoaded = false;
        draft.notFound = false;
        draft.loadError = false;
        draft.loading = true;
        draft.messageAppeared = false;
        draft.compactedSummary = null;
        draft.compactedBeforeId = null;
        draft.contextBranches = [];
        draft.contextPinnedFiles = [];
        draft.contextBranchesLoadError = null;
        draft.contextPinnedFilesLoadError = null;
        draft.lastCompactionMeta = null;
        draft.workspaceDir = null;
        draft.incognitoMode = false;
        draft.sandboxMode = false;
        draft.activeMoaPresetId = null;
        draft.securityPreset = normalizeSecurityPreset(draft.agentConfig?.defaultSecurityPreset);
        draft.chatId = id;
      });
      actions.clearCurrentSessionMessageId();
      loadMessages(id, actions);
      return;
    }

    const snapshot = resolveInstantChatSnapshot(id);

    if (snapshot) {
      actions.setMessages((draft) => {
        Object.assign(draft, snapshot);
        draft.chatId = id;
        draft.isMessagesLoaded = true;
        draft.securityPreset = normalizeSecurityPreset(draft.agentConfig?.defaultSecurityPreset);
        draft.activeMoaPresetId = snapshot.incognitoMode ? null : (snapshot.activeMoaPresetId ?? null);
      });
      actions.clearCurrentSessionMessageId();

      if (snapshot.loading) {
        return;
      }

      const silentActions = {
        ...actions,
        setMessages: (updater: (state: ChatState) => void) => {
          actions.setMessages((draft) => {
            if (draft.chatId === id) {
              const preservedLoading = draft.loading;
              const preservedIsMessagesLoaded = draft.isMessagesLoaded;
              updater(draft);
              draft.loading = preservedLoading;
              draft.isMessagesLoaded = preservedIsMessagesLoaded;
            }
          });
        },
      };
      loadMessages(id, silentActions, { preserveInstantSessionConfig: true }).catch(console.error);
    } else {
      actions.setMessages((draft) => {
        draft.messages = [];
        draft.isMessagesLoaded = false;
        draft.notFound = false;
        draft.loadError = false;
        draft.loading = true;
        draft.messageAppeared = false;
        draft.compactedSummary = null;
        draft.compactedBeforeId = null;
        draft.contextBranches = [];
        draft.contextPinnedFiles = [];
        draft.contextBranchesLoadError = null;
        draft.contextPinnedFilesLoadError = null;
        draft.lastCompactionMeta = null;
        draft.workspaceDir = null;
        draft.incognitoMode = false;
        draft.sandboxMode = false;
        draft.activeMoaPresetId = null;
        draft.securityPreset = normalizeSecurityPreset(draft.agentConfig?.defaultSecurityPreset);
        draft.chatId = id;
      });
      actions.clearCurrentSessionMessageId();
      loadMessages(id, actions);
    }
  }
};

function shouldApplyPaneMessages(lruSnapshot: Partial<ChatState>, paneSnapshot: Partial<ChatState>): boolean {
  if (paneSnapshot.loading === true) {
    return true;
  }

  const lruMessageCount = lruSnapshot.messages?.length ?? 0;
  const paneMessageCount = paneSnapshot.messages?.length ?? 0;
  return paneMessageCount > lruMessageCount;
}

export function resolveInstantChatSnapshot(chatId: string): Partial<ChatState> | null {
  const lruSnapshot = getChatNavigationSnapshot(chatId);
  const pane = useWorkspaceStore.getState().panes.find((entry) => entry.chatId === chatId);
  const paneSnapshot = pane?.snapshot ?? null;

  if (lruSnapshot && paneSnapshot) {
    const merged = mergeChatSessionConfig({ ...lruSnapshot }, paneSnapshot);

    if (shouldApplyPaneMessages(lruSnapshot, paneSnapshot) && paneSnapshot.messages !== undefined) {
      merged.messages = paneSnapshot.messages;
    }

    if (paneSnapshot.loading !== undefined) {
      merged.loading = paneSnapshot.loading;
    }

    if (paneSnapshot.messageAppeared !== undefined) {
      merged.messageAppeared = paneSnapshot.messageAppeared;
    }

    return merged;
  }

  return lruSnapshot ?? paneSnapshot;
}

export function persistActiveChatNavigationSnapshot(state: ChatState): void {
  if (!state.chatId || !state.isMessagesLoaded || state.incognitoMode) {
    return;
  }

  saveChatNavigationSnapshot(state.chatId, extractNavigationSnapshot(state));
}

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
