/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: Active chat state manager.)
 * - @/store/useWorkspaceStore::useWorkspaceStore (POS: Workspace state manager.)
 * - @/lib/deploy-mode::getApiBaseUrl (POS: 前端部署模式与基础地址解析层。)
 * - @/components/dev/e2eBridge/sendTurnContract::SEND_TURN_API_POLL_TIMEOUT_MS (POS: 发送回合中与 Python 端 dev_gate 契约逐值对应的常量)
 *
 * [OUTPUT]
 * - readE2eSendGeneration / bumpE2eSendGeneration: the send generation counter kept on `window`
 * - resolveE2eTurnProgress: user count, streaming flag and UI progress of one chat (workspace-pane aware)
 * - pollApiUserMessages / ApiPollStats: bounded message-list poll that tells "not persisted", "unknown chat" and "API unreachable" apart
 *
 * [POS]
 * 发送回合的进度读数：页面侧 store 进度、API 落库用户消息的有界轮询与发送代数计数，供 submitAndObserveTurn 判定封口。
 */
import useChatStore from '@/store/useChatStore';
import useWorkspaceStore from '@/store/useWorkspaceStore';
import { getApiBaseUrl } from '@/lib/deploy-mode';
import { SEND_TURN_API_POLL_TIMEOUT_MS } from '@/components/dev/e2eBridge/sendTurnContract';

const E2E_SEND_GENERATION_KEY = '__MYRM_E2E_SEND_GENERATION__';

export function readE2eSendGeneration(): number {
  const raw = (window as unknown as Record<string, unknown>)[E2E_SEND_GENERATION_KEY];
  return typeof raw === 'number' && Number.isFinite(raw) ? raw : 0;
}

export function bumpE2eSendGeneration(_reason: string): number {
  const next = readE2eSendGeneration() + 1;
  (window as unknown as Record<string, unknown>)[E2E_SEND_GENERATION_KEY] = next;
  return next;
}

/** Mirror createSmartUpdater routing so OBSERVE reads the same state SUBMIT writes. */
function resolveE2eProgressChatState(chatId: string): {
  messages: Array<{ role?: string }>;
  loading: boolean;
  abortController: AbortController | null;
} {
  const chatState = useChatStore.getState();
  const workspaceState = useWorkspaceStore.getState();
  if (!chatId || workspaceState.panes.length === 0) {
    return {
      messages: chatState.messages,
      loading: chatState.loading,
      abortController: chatState.abortController,
    };
  }
  const activePane = workspaceState.panes.find((pane) => pane.id === workspaceState.activePaneId);
  if (activePane?.chatId === chatId) {
    return {
      messages: chatState.messages,
      loading: chatState.loading,
      abortController: chatState.abortController,
    };
  }
  const pane = workspaceState.panes.find((entry) => entry.chatId === chatId);
  if (pane?.snapshot) {
    return {
      messages: pane.snapshot.messages ?? [],
      loading: Boolean(pane.snapshot.loading),
      abortController: pane.abortController ?? chatState.abortController,
    };
  }
  return {
    messages: chatState.messages,
    loading: chatState.loading,
    abortController: chatState.abortController,
  };
}

export function resolveE2eTurnProgress(
  chatId: string,
  baselineUsers: number,
): { userCount: number; streaming: boolean; uiProgress: boolean } {
  const chatState = useChatStore.getState();
  const workspaceState = useWorkspaceStore.getState();
  const progressState = resolveE2eProgressChatState(chatId);
  const pane = workspaceState.panes.find((entry) => entry.chatId === chatId);
  const paneAbort = pane?.id ? workspaceState.getPaneAbortController(pane.id) : null;
  const userCount = progressState.messages.filter((msg) => msg.role === 'user').length;
  const streaming = Boolean(
    progressState.loading ||
    progressState.abortController ||
    paneAbort ||
    chatState.loading ||
    chatState.abortController,
  );
  return {
    userCount,
    streaming,
    uiProgress: userCount > baselineUsers || streaming,
  };
}

interface ApiUserPoll {
  users: number;
  /** HTTP 404: the API does not know the chat, which a new chat stays until its first assistant output. */
  notFound: boolean;
  /** Why the API could not be asked or did not answer; null when it answered or said 404. */
  failure: string | null;
}

export interface ApiPollStats {
  polls: number;
  notFound: number;
  failures: number;
  lastFailure: string | null;
  /** Slowest answer or abort, in ms: how close the polls ran to SEND_TURN_API_POLL_TIMEOUT_MS. */
  slowestMs: number;
}

function describeApiPollFailure(error: unknown): string {
  if (error instanceof DOMException && error.name === 'TimeoutError') {
    return 'timeout';
  }
  return error instanceof Error ? `${error.name}: ${error.message}` : String(error);
}

/**
 * "The user row is not persisted", "the API does not know the chat yet" and "the API could not
 * be asked" all read as zero users, so a poll says which one it was and the turn counts them.
 */
export async function pollApiUserMessages(chatId: string): Promise<ApiUserPoll> {
  const messagesUrl = `${getApiBaseUrl().replace(/\/+$/, '')}/chats/${encodeURIComponent(chatId)}/messages`;
  try {
    const resp = await fetch(messagesUrl, {
      cache: 'no-store',
      signal: AbortSignal.timeout(SEND_TURN_API_POLL_TIMEOUT_MS),
    });
    if (resp.status === 404) {
      return { users: 0, notFound: true, failure: null };
    }
    if (!resp.ok) {
      return { users: 0, notFound: false, failure: `http-${resp.status}` };
    }
    const payload = (await resp.json()) as {
      data?: { messages?: Array<{ role?: string }> };
    };
    const users = payload.data?.messages?.filter((entry) => entry.role === 'user').length ?? 0;
    return { users, notFound: false, failure: null };
  } catch (error) {
    return { users: 0, notFound: false, failure: describeApiPollFailure(error) };
  }
}
