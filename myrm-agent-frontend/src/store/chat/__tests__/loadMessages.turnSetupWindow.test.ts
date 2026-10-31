import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatState, Message } from '@/store/chat/types';
import { loadMessages } from '@/store/chat/messageManagement';

/**
 * A page opened right after a message was sent finds the chat in the turn's startup window: the user row is stored and the
 * server runs the chat, but the stream a page attaches to is only registered after the pre-reply compaction and the history
 * load. Attaching then answers "no stream", and the page has to keep trying while the server still runs the chat.
 */

const RETRY_INTERVAL_MS = 500;
const RETRY_BUDGET_MS = 60_000;

const getChatDetailMock = vi.hoisted(() => vi.fn());
const getMessagesMock = vi.hoisted(() => vi.fn());
const attachToChatMock = vi.hoisted(() => vi.fn());
const apiRequestMock = vi.hoisted(() => vi.fn());

const mockStore = vi.hoisted(() => {
  const store: Record<string, unknown> = {
    chatId: 'chat-starting',
    messages: [] as unknown[],
    loading: false,
    isMessagesLoaded: false,
    abortController: null,
    setContextPinnedFiles: vi.fn(),
    setContextPinnedFilesLoadError: vi.fn(),
    setContextBranches: vi.fn(),
    setContextBranchesLoadError: vi.fn(),
    setSandboxMode: vi.fn(),
    setAgentConfig: vi.fn(),
    fetchTurnOutlines: vi.fn().mockResolvedValue(undefined),
  };
  return store;
});

vi.mock('@/services/chat', () => ({
  getChatDetail: (...args: unknown[]) => getChatDetailMock(...args),
  getMessages: (...args: unknown[]) => getMessagesMock(...args),
  generateChatTitle: vi.fn(),
  updateChatTitle: vi.fn(),
  getContextPins: vi.fn().mockResolvedValue({ files: [] }),
  listContextBranches: vi.fn().mockResolvedValue([]),
}));

vi.mock('@/lib/api', () => ({
  apiRequest: (...args: unknown[]) => apiRequestMock(...args),
  ApiError: class ApiError extends Error {},
}));

vi.mock('@/store/useWorkspaceStore', () => ({ default: { getState: () => ({ panes: [] }) } }));
vi.mock('@/store/useChatStore', () => ({ default: { getState: () => mockStore } }));
vi.mock('@/store/useAgentStore', () => ({
  default: { getState: () => ({ fetchAgent: vi.fn().mockResolvedValue(null) }) },
}));
vi.mock('@/store/useConfigStore', () => ({ default: { getState: () => ({}) } }));
vi.mock('@/store/useProjectStore', () => ({
  useProjectStore: { getState: () => ({ activeFilter: undefined }) },
}));
vi.mock('@/services/uploadController', () => ({ abortCurrentUpload: vi.fn() }));
vi.mock('@/store/chat/messageRequest', () => ({
  attachToChat: attachToChatMock,
  attachForHitlRecovery: vi.fn(),
}));
vi.mock('@/store/chat/chatAgentSessionRestore', () => ({
  restoreAgentConfigFromChat: vi.fn().mockResolvedValue(undefined),
}));

const TURN_STATE_ENDPOINT = /^\/agents\/chat\/([^/]+)\/turn-state$/;

function makeActions(): Parameters<typeof loadMessages>[1] {
  return {
    setMessages: (updater: (draft: ChatState) => void) => updater(mockStore as unknown as ChatState),
  } as unknown as Parameters<typeof loadMessages>[1];
}

/** The chat as the page finds it: only the user's message is stored. */
function onlyTheUserMessageIsStored(): void {
  getMessagesMock.mockResolvedValue({
    messages: [
      {
        messageId: 'msg-user',
        chatId: 'chat-starting',
        createdAt: new Date('2026-08-08T00:00:00.000Z'),
        role: 'user',
        content: 'say OK',
      } as unknown as Message,
    ],
    has_more: false,
    next_cursor: null,
  });
}

/** The server runs the chat for the next `count` turn-state reads, then reports it idle. */
function serverRunsTheChatFor(count: number): void {
  let remaining = count;
  apiRequestMock.mockImplementation(async (endpoint: string) => {
    if (!TURN_STATE_ENDPOINT.test(endpoint)) {
      return { active: false };
    }
    const running = remaining > 0;
    remaining -= 1;
    return { running, awaitingApproval: false };
  });
}

function turnStateReads(): number {
  return apiRequestMock.mock.calls.filter(([endpoint]) => TURN_STATE_ENDPOINT.test(endpoint)).length;
}

/** Lets the fire-and-forget recovery `loadMessages` starts run until it waits on a timer or ends. */
async function advance(ms: number): Promise<void> {
  await vi.advanceTimersByTimeAsync(ms);
}

describe('loadMessages while the turn is still starting', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    mockStore.chatId = 'chat-starting';
    mockStore.messages = [];
    mockStore.loading = false;
    mockStore.isMessagesLoaded = false;
    mockStore.abortController = null;
    getChatDetailMock.mockResolvedValue({
      chat: {
        actionMode: 'agent',
        compacted_summary: null,
        compacted_before_id: null,
        workspace_dir: null,
        session_loaded_skill_names: null,
        is_incognito: false,
        agent_id: null,
      },
    });
    onlyTheUserMessageIsStored();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('keeps attaching while the server runs the chat, and does not refetch once it is attached', async () => {
    attachToChatMock.mockResolvedValueOnce(false).mockResolvedValueOnce(false).mockResolvedValue(true);
    serverRunsTheChatFor(Number.POSITIVE_INFINITY);

    await loadMessages('chat-starting', makeActions());
    await advance(0);
    expect(attachToChatMock).toHaveBeenCalledTimes(1);

    await advance(RETRY_INTERVAL_MS);
    expect(attachToChatMock).toHaveBeenCalledTimes(2);
    await advance(RETRY_INTERVAL_MS);
    expect(attachToChatMock).toHaveBeenCalledTimes(3);

    await advance(RETRY_BUDGET_MS);
    expect(attachToChatMock).toHaveBeenCalledTimes(3);
    expect(getMessagesMock).toHaveBeenCalledTimes(1);
  });

  it('refetches the stored messages once the server reports the chat idle', async () => {
    attachToChatMock.mockResolvedValue(false);
    // The first read is the sample `loadMessages` takes before it fetches; the second is the one that decides the first retry.
    serverRunsTheChatFor(2);

    await loadMessages('chat-starting', makeActions());
    await advance(0);
    expect(getMessagesMock).toHaveBeenCalledTimes(1);

    await advance(RETRY_INTERVAL_MS);
    await advance(0);

    expect(attachToChatMock).toHaveBeenCalledTimes(2);
    expect(getMessagesMock).toHaveBeenCalledTimes(2);
  });

  it('refetches without retrying when the server does not run the chat', async () => {
    attachToChatMock.mockResolvedValue(false);
    serverRunsTheChatFor(0);

    await loadMessages('chat-starting', makeActions());
    await advance(0);

    expect(attachToChatMock).toHaveBeenCalledTimes(1);
    expect(getMessagesMock).toHaveBeenCalledTimes(2);
    expect(turnStateReads()).toBe(2);
  });

  it('gives up after the budget and falls back to refetching the stored messages', async () => {
    attachToChatMock.mockResolvedValue(false);
    serverRunsTheChatFor(Number.POSITIVE_INFINITY);

    await loadMessages('chat-starting', makeActions());
    await advance(RETRY_BUDGET_MS + RETRY_INTERVAL_MS);

    const attempts = attachToChatMock.mock.calls.length;
    expect(attempts).toBeGreaterThan(RETRY_BUDGET_MS / RETRY_INTERVAL_MS - 2);
    expect(attempts).toBeLessThanOrEqual(RETRY_BUDGET_MS / RETRY_INTERVAL_MS + 1);
    expect(getMessagesMock).toHaveBeenCalledTimes(2);

    await advance(RETRY_BUDGET_MS);
    expect(attachToChatMock).toHaveBeenCalledTimes(attempts);
  });

  it('stops, without refetching, when the user opened another chat while it waited', async () => {
    attachToChatMock.mockResolvedValue(false);
    serverRunsTheChatFor(Number.POSITIVE_INFINITY);

    await loadMessages('chat-starting', makeActions());
    await advance(0);
    mockStore.chatId = 'chat-other';

    await advance(RETRY_BUDGET_MS);

    expect(attachToChatMock).toHaveBeenCalledTimes(1);
    expect(getMessagesMock).toHaveBeenCalledTimes(1);
    expect(mockStore.chatId).toBe('chat-other');
  });

  it('stops, without refetching, when the user started a turn while it waited', async () => {
    attachToChatMock.mockResolvedValue(false);
    serverRunsTheChatFor(Number.POSITIVE_INFINITY);

    await loadMessages('chat-starting', makeActions());
    await advance(0);
    mockStore.loading = true;

    await advance(RETRY_BUDGET_MS);

    expect(attachToChatMock).toHaveBeenCalledTimes(1);
    expect(getMessagesMock).toHaveBeenCalledTimes(1);
  });

  it('runs one waiting loop per chat: a second load while it waits does not start another', async () => {
    attachToChatMock.mockResolvedValueOnce(false).mockResolvedValue(true);
    serverRunsTheChatFor(Number.POSITIVE_INFINITY);

    await loadMessages('chat-starting', makeActions());
    await advance(0);
    await loadMessages('chat-starting', makeActions());
    await advance(0);
    expect(attachToChatMock).toHaveBeenCalledTimes(1);

    await advance(RETRY_INTERVAL_MS);

    expect(attachToChatMock).toHaveBeenCalledTimes(2);
  });

  it('ends the recovery when a retry fails, and lets the next load start a new one', async () => {
    attachToChatMock.mockResolvedValueOnce(false).mockRejectedValueOnce(new Error('Attach failed: Bad Gateway'));
    serverRunsTheChatFor(Number.POSITIVE_INFINITY);
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    await loadMessages('chat-starting', makeActions());
    await advance(RETRY_INTERVAL_MS);
    expect(attachToChatMock).toHaveBeenCalledTimes(2);
    await advance(RETRY_BUDGET_MS);
    expect(attachToChatMock).toHaveBeenCalledTimes(2);

    attachToChatMock.mockResolvedValue(true);
    await loadMessages('chat-starting', makeActions());
    await advance(0);

    expect(attachToChatMock).toHaveBeenCalledTimes(3);
  });
});
