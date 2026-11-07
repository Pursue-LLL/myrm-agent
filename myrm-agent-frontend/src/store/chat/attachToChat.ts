/**
 * [INPUT]
 * ./consumeStream::consumeStream (POS: Single-segment SSE consumer)
 * @/store/chat/chatAgentSessionRestore::finalizeAgentStreamTurn (POS: Reconcile store with the DB agent binding)
 *
 * [OUTPUT]
 * attachForHitlRecovery: Bounded attach that brings back the tool-approval card of a turn parked behind it, without holding the page's turn state open.
 * attachToChat: Re-attach to a chat's running turn over its attach SSE stream; post-consume finalizeAgentStreamTurn; ending never resets the turn state of a newer turn.
 *
 * [POS]
 * Attach side of the chat stream: re-joins a turn that keeps running on the server (reload, reconnect, parked approval).
 */

import { resolveE2eApiBase } from '@/lib/deploy-mode';
import { fetchWithTimeout } from '@/lib/api';
import { ensureMobileE2EE, withMobilePairHeaders } from '@/lib/mobileRemote';
import { FatalNetworkError, isRetryableHttpStatus } from '@/lib/utils/networkResilience';
import { finalizeAgentStreamTurn } from '@/store/chat/chatAgentSessionRestore';
import type { ChatState } from '@/store/chat/types';
import useToolApprovalStore from '../useToolApprovalStore';
import useWorkspaceStore, { type PaneConfig } from '../useWorkspaceStore';
import type { ChatActionsMethods, ChatActionsState } from './chatActions';
import { consumeStream } from './consumeStream';
import { isHeldByOtherTurn } from './sendLifecycle';
import { createSmartUpdater } from './smartUpdater';

export type AttachToChatOptions = {
  /** SHPOIB E2E / stream recovery: attach while the primary POST stream still holds loading. */
  allowWhileLoading?: boolean;
};

export type HitlRecoveryResult = {
  ok: true;
  attached: boolean;
  queueLen: number;
  source: 'attach' | 'probe' | 'none';
};

const HITL_ATTACH_RECOVERY_MS = 12_000;

/** Cards waiting for this chat: the queue is shared by every chat, so the cards of other chats say nothing about this one. */
function approvalsQueuedFor(chatId: string): number {
  return useToolApprovalStore.getState().queue.filter((request) => request.chatId === chatId).length;
}

async function replayPendingHitlFromProbe(
  chatId: string,
  state: ChatActionsState,
  actions: ChatActionsMethods,
): Promise<number> {
  if (!resolveE2eApiBase()) {
    return approvalsQueuedFor(chatId);
  }
  try {
    const response = await fetchWithTimeout(
      `/security/allowlist/test/hitl-probe?chat_id=${encodeURIComponent(chatId)}`,
      { method: 'GET' },
      10_000,
    );
    if (!response.ok) {
      return approvalsQueuedFor(chatId);
    }
    const probe = (await response.json()) as { pending_interrupt_events?: unknown[] };
    const events = probe.pending_interrupt_events;
    if (!Array.isArray(events) || events.length === 0) {
      return approvalsQueuedFor(chatId);
    }

    const { handleMessageStream } = await import('./messageStream/handleMessageStream');
    const { parseSseEnvelope } = await import('./schema');
    const { AdaptiveScheduler } = await import('./adaptiveScheduler');
    const scheduler = new AdaptiveScheduler();
    const streamState = {
      chatId: state.chatId || chatId,
      messages: state.messages,
      messageAppeared: state.messageAppeared,
      loading: state.loading,
      scheduler,
    };
    const streamActions = {
      setMessages: (updater: (draft: ChatActionsState) => void) => {
        actions.setMessages((draft) => updater(draft));
      },
      setMessageAppeared: actions.setMessageAppeared,
      setLoading: actions.setLoading,
      _processSuggestions: actions._processSuggestions,
      scheduleAutoSave: actions.scheduleAutoSave,
    };
    let added = false;
    let recievedMessage = '';
    for (const raw of events) {
      const event = parseSseEnvelope(raw);
      if (!event) {
        continue;
      }
      ({ added, recievedMessage } = await handleMessageStream(
        event,
        '',
        undefined,
        added,
        recievedMessage,
        streamState,
        streamActions,
        state.files,
      ));
      if (approvalsQueuedFor(chatId) > 0) {
        break;
      }
    }
    scheduler.flush();
    scheduler.cancel();
  } catch (error) {
    console.warn('SHPOIB HITL probe replay failed:', error);
  }
  return approvalsQueuedFor(chatId);
}

/**
 * Bounded attach that brings back the tool-approval card of a turn parked behind it, without holding the page's turn state open
 * (the collector of a parked turn never ends its attach stream). Used by the reload recovery in `loadMessages` and by the SHPOIB E2E bridge.
 */
export const attachForHitlRecovery = async (
  chatId: string,
  actions: ChatActionsMethods,
  get: () => ChatState,
): Promise<HitlRecoveryResult> => {
  const normalized = chatId.trim();
  if (!normalized) {
    return { ok: true, attached: false, queueLen: 0, source: 'none' };
  }

  const existingQueue = approvalsQueuedFor(normalized);
  if (existingQueue > 0) {
    return { ok: true, attached: true, queueLen: existingQueue, source: 'attach' };
  }

  const state = get();
  const smartSetMessages = createSmartUpdater(normalized, actions.setMessages);
  const smartActions = { ...actions, setMessages: smartSetMessages };
  const attachAbort = new AbortController();

  try {
    await ensureMobileE2EE();
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
    const headers = withMobilePairHeaders({
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    });

    const response = await fetchWithTimeout(
      `/agents/chat/${normalized}/attach`,
      {
        method: 'GET',
        headers,
        signal: attachAbort.signal,
      },
      0,
    );

    if (!response.ok) {
      const queueLen = await replayPendingHitlFromProbe(normalized, get(), smartActions);
      return {
        ok: true,
        attached: queueLen > 0,
        queueLen,
        source: queueLen > 0 ? 'probe' : 'none',
      };
    }
    if (!response.body) {
      const queueLen = await replayPendingHitlFromProbe(normalized, get(), smartActions);
      return {
        ok: true,
        attached: queueLen > 0,
        queueLen,
        source: queueLen > 0 ? 'probe' : 'none',
      };
    }

    await consumeStream(response, '', state, smartActions, attachAbort, false, '', {
      untilApprovalQueuedFor: normalized,
      maxWaitMs: HITL_ATTACH_RECOVERY_MS,
    });
    const queuedForChat = approvalsQueuedFor(normalized);
    if (queuedForChat > 0) {
      return {
        ok: true,
        attached: true,
        queueLen: queuedForChat,
        source: 'attach',
      };
    }

    const queueLen = await replayPendingHitlFromProbe(normalized, get(), smartActions);
    return {
      ok: true,
      attached: queueLen > 0,
      queueLen,
      source: queueLen > 0 ? 'probe' : 'none',
    };
  } catch (error) {
    console.warn('SHPOIB HITL attach recovery failed:', error);
    const queueLen = await replayPendingHitlFromProbe(normalized, get(), smartActions);
    return {
      ok: true,
      attached: queueLen > 0,
      queueLen,
      source: queueLen > 0 ? 'probe' : 'none',
    };
  } finally {
    attachAbort.abort();
  }
};

export const attachToChat = async (
  chatId: string,
  actions: ChatActionsMethods,
  get: () => ChatState,
  options?: AttachToChatOptions,
): Promise<boolean> => {
  const state = get();
  if (state.loading && !options?.allowWhileLoading) {
    return false;
  }

  const smartSetMessages = createSmartUpdater(chatId, actions.setMessages);
  const smartActions = { ...actions, setMessages: smartSetMessages };

  const abortController = new AbortController();

  const paneId = useWorkspaceStore.getState().panes.find((p: PaneConfig) => p.chatId === chatId)?.id;
  if (paneId) {
    useWorkspaceStore.getState().setPaneAbortController(paneId, abortController);
  }

  smartActions.setMessages((draft) => {
    draft.loading = true;
    draft.abortController = abortController;
  });

  try {
    await ensureMobileE2EE();
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
    const headers = withMobilePairHeaders({
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    });

    const response = await fetchWithTimeout(
      `/agents/chat/${chatId}/attach`,
      {
        method: 'GET',
        headers,
        signal: abortController.signal,
      },
      0,
    );

    if (!response.ok) {
      if (response.status === 404) {
        // No active task — still reconcile store with DB agent binding.
        await finalizeAgentStreamTurn(chatId);
        return false;
      }
      if (!isRetryableHttpStatus(response.status)) {
        throw new FatalNetworkError(`Attach failed: ${response.statusText}`, response.status);
      }
      throw new Error(`Attach failed: ${response.statusText}`);
    }

    if (!response.body) {
      await finalizeAgentStreamTurn(chatId);
      return false;
    }

    await consumeStream(response, '', state, smartActions, abortController, false, '');
    await finalizeAgentStreamTurn(chatId);
    return true;
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      console.log('Attach stream aborted');
    } else {
      console.error('Attach stream error:', error);
      throw error;
    }
    return false;
  } finally {
    // The attach can end after a newer turn took over (it was still reconciling with the server): that turn owns the state.
    let heldByOtherTurn = false;
    smartActions.setMessages((draft) => {
      heldByOtherTurn = isHeldByOtherTurn(draft.abortController, abortController);
      if (heldByOtherTurn) {
        return;
      }
      draft.loading = false;
      draft.abortController = null;
    });
    if (paneId && !heldByOtherTurn) {
      useWorkspaceStore.getState().setPaneAbortController(paneId, null);
    }
  }
};
