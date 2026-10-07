/**
 * [INPUT]
 * @/services/chat::getChatDetail, getMessages (POS: Chat API client)
 * ./messageHydration::parseMessages (POS: persisted message normalization)
 *
 * [OUTPUT]
 * loadMessages: Fetch chat history; agent-bound chats defer isMessagesLoaded until restore completes.
 * loadOlderMessages / loadThroughTurn: Paginate history.
 *
 * [POS]
 * Chat history loader (DB fetch, hydration, active-turn attach). Reads useChatStore, so the store only imports it lazily.
 * Session switching lives in chatSessionInit.ts; title auto-save in chatTitleAutoSave.ts.
 */

import type { ActionMode } from '@/store/chat/types';
import type { ChatActionsMethods } from './messageRequest';
import { getChatDetail, getMessages, getContextPins, listContextBranches } from '@/services/chat';
import { ApiError, apiRequest } from '@/lib/api';
import { stripUserMessageDisplayText } from '@/lib/utils/messageUtils';
import useChatStore from '@/store/useChatStore';
import { restoreAgentConfigFromChat } from '@/store/chat/chatAgentSessionRestore';
import { shouldDeferMessagesReadyUntilAgentRestore } from '@/store/chat/sessionAgentHydration';
import { normalizeSessionAccessRoots } from '@/store/chat/types/sessionAccess';
import { resolveHydratedMoaPresetId, writeStoredMoaPresetId } from '@/store/chat/moaPresetStorage';
import { parseMessages } from './messageHydration';

const VALID_ACTION_MODES: readonly ActionMode[] = ['fast', 'agent', 'deep_research'];

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
 * 加载历史消息（初始加载最新一页）
 */
export const loadMessages = async (
  chatId: string,
  actions: ChatActionsMethods,
  options?: LoadMessagesOptions,
): Promise<void> => {
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
        state.turnOutlines = chatData.turn_outline || [];
        state.workspaceDir = chatData.chat.workspace_dir;
        state.sessionSkillOverrides = chatData.chat.session_loaded_skill_names;
        state.sessionAccessRoots = normalizeSessionAccessRoots(chatData.chat.session_access_roots);
        state.hasMoreMessages = page.has_more;
        state.nextCursor = page.next_cursor;
      }
    });

    const agentIdForRestore = chatData.chat.agent_id?.trim() || null;
    const deferReadyUntilAgentRestore = shouldDeferMessagesReadyUntilAgentRestore(agentIdForRestore);

    if (deferReadyUntilAgentRestore) {
      actions.setMessages((state) => {
        if (state.chatId === chatId) {
          state.loading = true;
          state.isMessagesLoaded = false;
        }
      });
    } else {
      actions.setMessages((state) => {
        if (state.chatId === chatId) {
          state.isMessagesLoaded = true;
          state.loading = false;
        }
      });
    }

    // Agent binding always follows DB chat.agent_id, even when instant-session
    // snapshot preserved messages/loading (LRU attach must not keep stale agentConfig).
    await restoreAgentConfigFromChat(chatId, chatData.chat.agent_id);

    if (deferReadyUntilAgentRestore) {
      actions.setMessages((state) => {
        if (state.chatId === chatId) {
          state.isMessagesLoaded = true;
          state.loading = false;
        }
      });
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

    // 恢复当前会话已绑定的共享知识库上下文 (Restores session-bound shared knowledge bases)
    import('@/services/memory/sharedContexts')
      .then(async ({ listSharedContexts, listSharedContextBindingsForTarget }) => {
        try {
          const [bindRes, ctxRes] = await Promise.all([
            listSharedContextBindingsForTarget('conversation', chatId),
            listSharedContexts('active'),
          ]);
          if (useChatStore.getState().chatId === chatId) {
            const loadedContexts = ctxRes.items || [];
            const activeIds = bindRes.items.map((b) => b.context_id);
            const activeNames: Record<string, string> = {};
            bindRes.items.forEach((b) => {
              const matched = loadedContexts.find((c) => c.id === b.context_id);
              if (matched) {
                activeNames[b.context_id] = matched.name;
              }
            });
            useChatStore.getState().setActiveKnowledgeBaseIds(activeIds, activeNames);
          }
        } catch {
          // 静默降级
        }
      })
      .catch(() => {});

    // 自动刷新轻量会话大纲投影 (Auto refresh lightweight turn outlines)
    void useChatStore.getState().fetchTurnOutlines(chatId);
  } catch (error) {
    console.error('Failed to load chat messages:', error, chatId);

    actions.setMessages((state) => {
      if (state.chatId === chatId) {
        const isNotFound = error instanceof ApiError && (error.code === 40004 || error.code === 404);
        state.notFound = isNotFound;
        state.loadError = !isNotFound; // 非 404 的错误都视为加载错误
        state.isMessagesLoaded = isNotFound;
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
        const existingIds = new Set(s.messages.map((m) => m.messageId));
        const uniqueOlder = olderMessages.filter((m) => !existingIds.has(m.messageId));
        s.messages = [...uniqueOlder, ...s.messages];
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

/**
 * 连续批量向前翻页加载直至目标消息 (轮次用户消息ID) 被完全载入到内存 (loadThroughTurn 投影导轨驱动器)
 */
export const loadThroughTurn = async (targetMessageId: string, actions: ChatActionsMethods): Promise<boolean> => {
  const state = useChatStore.getState();
  if (!state.chatId || !targetMessageId) {
    return false;
  }

  const isLoaded = () => {
    const current = useChatStore.getState();
    return current.messages.some((m) => m.messageId === targetMessageId);
  };

  if (isLoaded()) {
    return true;
  }

  // 循环加载更早页直到目标消息进入列表或没有更多历史消息
  let maxRounds = 25; // 保护上限，防止死循环
  while (!isLoaded() && maxRounds > 0) {
    const current = useChatStore.getState();
    if (!current.hasMoreMessages || !current.nextCursor || current.loadingOlder) {
      break;
    }
    await loadOlderMessages(actions);
    maxRounds--;
  }

  return isLoaded();
};
