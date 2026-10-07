/**
 * [INPUT]
 * ./chatNavigationSnapshotCache::getChatNavigationSnapshot, saveChatNavigationSnapshot (POS: LRU navigation snapshots)
 * @/store/useWorkspaceStore::useWorkspaceStore (POS: Workspace pane snapshots)
 * ./messageManagement::loadMessages (POS: history loader, lazily imported)
 *
 * [OUTPUT]
 * initializeChat: Initialize or switch chat sessions with instant snapshot rendering.
 * resolveInstantChatSnapshot: Resolve workspace pane or LRU snapshot for a chat id.
 * persistActiveChatNavigationSnapshot: Persist the active chat into the LRU snapshot cache.
 *
 * [POS]
 * Synchronous session-switch layer used by useChatStore.initializeChat. It must not statically import
 * messageManagement (which reads useChatStore), so history loading is deferred via dynamic import.
 */

import crypto from 'crypto';
import type { Message, ChatState } from '@/store/chat/types';
import type { ChatActionsMethods } from './messageRequest';
import type { LoadMessagesOptions } from './messageManagement';
import useWorkspaceStore from '@/store/useWorkspaceStore';
import {
  extractNavigationSnapshot,
  getChatNavigationSnapshot,
  saveChatNavigationSnapshot,
} from '@/store/chat/chatNavigationSnapshotCache';
import { normalizeSecurityPreset } from '@/store/chat/securityPreset';
import { mergeChatSessionConfig } from '@/store/chat/chatSessionConfig';
import { abortCurrentUpload } from '@/services/uploadController';

/** Deferred so this module never forms an import cycle with the store-reading history loader. */
const loadMessages = async (
  chatId: string,
  actions: ChatActionsMethods,
  options?: LoadMessagesOptions,
): Promise<void> => {
  const { loadMessages: load } = await import('./messageManagement');
  return load(chatId, actions, options);
};

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
      const snapshotHasBoundAgent = Boolean(snapshot.agentConfig?.agentId);
      actions.setMessages((draft) => {
        Object.assign(draft, snapshot);
        draft.chatId = id;
        // Agent-bound chats: background loadMessages+restore owns ready signal (BUG-004 gate).
        draft.isMessagesLoaded = snapshotHasBoundAgent ? false : true;
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
            if (draft.chatId !== id) {
              return;
            }
            const lockStreamingLoading = snapshot.loading;
            const lockedLoading = lockStreamingLoading ? draft.loading : null;
            updater(draft);
            if (lockStreamingLoading && lockedLoading !== null) {
              draft.loading = lockedLoading;
            }
            // isMessagesLoaded: never preserve — loadMessages Hydration Readiness Gate owns it.
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
