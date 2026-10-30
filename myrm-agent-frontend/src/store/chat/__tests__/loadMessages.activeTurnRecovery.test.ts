import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatState, Message } from '@/store/chat/types';
import { loadMessages } from '@/store/chat/messageManagement';

const getChatDetailMock = vi.hoisted(() => vi.fn());
const getMessagesMock = vi.hoisted(() => vi.fn());
const attachToChatMock = vi.hoisted(() => vi.fn());
const attachForHitlRecoveryMock = vi.hoisted(() => vi.fn());
const apiRequestMock = vi.hoisted(() => vi.fn());
const restoreAgentConfigFromChatMock = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));

const mockStore = vi.hoisted(() => {
  const store: Record<string, unknown> = {
    chatId: 'chat-active',
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
  ApiError: class ApiError extends Error {
    code: number;
    constructor(code: number) {
      super('api error');
      this.code = code;
    }
  },
}));

vi.mock('@/store/useWorkspaceStore', () => ({
  default: {
    getState: () => ({ panes: [] }),
  },
}));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => mockStore,
  },
}));

vi.mock('@/store/useAgentStore', () => ({
  default: {
    getState: () => ({ fetchAgent: vi.fn().mockResolvedValue(null) }),
  },
}));

vi.mock('@/store/useConfigStore', () => ({
  default: {
    getState: () => ({}),
  },
}));

vi.mock('@/store/useProjectStore', () => ({
  useProjectStore: {
    getState: () => ({ activeFilter: undefined }),
  },
}));

vi.mock('@/services/uploadController', () => ({
  abortCurrentUpload: vi.fn(),
}));

vi.mock('@/store/chat/messageRequest', () => ({
  attachToChat: attachToChatMock,
  attachForHitlRecovery: attachForHitlRecoveryMock,
}));

vi.mock('@/store/chat/chatAgentSessionRestore', () => ({
  restoreAgentConfigFromChat: (...args: unknown[]) => restoreAgentConfigFromChatMock(...args),
}));

function setupStore(chatId: string): void {
  mockStore.chatId = chatId;
  mockStore.messages = [];
  mockStore.loading = false;
  mockStore.isMessagesLoaded = false;
  mockStore.abortController = null;
}

function makeActions(): Parameters<typeof loadMessages>[1] {
  return {
    setMessages: (updater: (draft: ChatState) => void) => updater(mockStore as unknown as ChatState),
  } as unknown as Parameters<typeof loadMessages>[1];
}

function chatDetailPayload(): { chat: Record<string, unknown> } {
  return {
    chat: {
      actionMode: 'agent',
      compacted_summary: null,
      compacted_before_id: null,
      workspace_dir: null,
      session_loaded_skill_names: null,
      is_incognito: false,
      agent_id: null,
    },
  };
}

const ACTIVE_SESSIONS_ENDPOINT = '/agents/active-sessions';

/**
 * What the server reports about its chats: the ones executing a turn right now, and the ones parked behind a tool-approval card.
 * Every other endpoint answers like an idle sandbox.
 */
function serverReports(running: string[], awaitingApproval: string[] = []): void {
  apiRequestMock.mockImplementation(async (endpoint: string) =>
    endpoint === ACTIVE_SESSIONS_ENDPOINT
      ? {
          activeSessions: running.map((chatId) => ({ chatId })),
          awaitingApprovalChatIds: awaitingApproval,
        }
      : { active: false },
  );
}

function activeSessionProbes(): unknown[][] {
  return apiRequestMock.mock.calls.filter(([endpoint]) => endpoint === ACTIVE_SESSIONS_ENDPOINT);
}

function lastMessageIs(role: 'user' | 'assistant'): void {
  getMessagesMock.mockResolvedValue({
    messages: [
      {
        messageId: `msg-${role}`,
        chatId: 'chat-active',
        createdAt: new Date('2026-08-08T00:00:00.000Z'),
        role,
        content: role === 'user' ? '只回复 OK' : '',
      } as unknown as Message,
    ],
    has_more: false,
    next_cursor: null,
  });
}

/** Lets the fire-and-forget recovery that `loadMessages` starts run to its end. */
async function settleRecovery(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe('loadMessages active-turn SSE recovery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getChatDetailMock.mockResolvedValue(chatDetailPayload());
    attachToChatMock.mockResolvedValue(true);
    attachForHitlRecoveryMock.mockResolvedValue({ ok: true, attached: true, queueLen: 1, source: 'attach' });
    serverReports([]);
  });

  it('attaches to resume a possibly in-flight agent turn when last message is a user message', async () => {
    setupStore('chat-active');
    getMessagesMock.mockResolvedValue({
      messages: [
        {
          messageId: 'msg-user',
          chatId: 'chat-active',
          createdAt: new Date('2026-08-08T00:00:00.000Z'),
          role: 'user',
          content: '只回复 OK',
        } as unknown as Message,
      ],
      has_more: false,
      next_cursor: null,
    });

    await loadMessages('chat-active', makeActions());

    await vi.waitFor(() => {
      expect(attachToChatMock).toHaveBeenCalledTimes(1);
    });
    expect(attachToChatMock).toHaveBeenCalledWith('chat-active', expect.anything(), expect.any(Function));
  });

  it('does not attach when the last message is an assistant reply', async () => {
    setupStore('chat-active');
    getMessagesMock.mockResolvedValue({
      messages: [
        {
          messageId: 'msg-asm',
          chatId: 'chat-active',
          createdAt: new Date('2026-08-08T00:00:00.000Z'),
          role: 'assistant',
          content: 'OK',
        } as unknown as Message,
      ],
      has_more: false,
      next_cursor: null,
    });

    await loadMessages('chat-active', makeActions());

    expect(attachToChatMock).not.toHaveBeenCalled();
  });

  it('attaches when the last message is an assistant message and the server is still running the chat', async () => {
    setupStore('chat-active');
    lastMessageIs('assistant');
    serverReports(['chat-active']);

    await loadMessages('chat-active', makeActions());

    await vi.waitFor(() => {
      expect(attachToChatMock).toHaveBeenCalledTimes(1);
    });
    expect(activeSessionProbes()).toHaveLength(1);
    expect(attachToChatMock).toHaveBeenCalledWith('chat-active', expect.anything(), expect.any(Function));
  });

  it('does not attach when the server only runs another chat', async () => {
    setupStore('chat-active');
    lastMessageIs('assistant');
    serverReports(['chat-other']);

    await loadMessages('chat-active', makeActions());
    await vi.waitFor(() => {
      expect(activeSessionProbes()).toHaveLength(1);
    });
    await settleRecovery();

    expect(attachToChatMock).not.toHaveBeenCalled();
  });

  it('does not attach, and does not fail the load, when the active-session probe fails', async () => {
    setupStore('chat-active');
    lastMessageIs('assistant');
    apiRequestMock.mockImplementation(async (endpoint: string) => {
      if (endpoint === ACTIVE_SESSIONS_ENDPOINT) {
        throw new Error('probe failed');
      }
      return { active: false };
    });

    await expect(loadMessages('chat-active', makeActions())).resolves.toBeUndefined();
    await vi.waitFor(() => {
      expect(activeSessionProbes()).toHaveLength(1);
    });
    await settleRecovery();

    expect(attachToChatMock).not.toHaveBeenCalled();
    expect(mockStore.isMessagesLoaded).toBe(true);
  });

  it('samples whether the server runs the chat before it fetches the messages', async () => {
    setupStore('chat-active');
    lastMessageIs('assistant');

    await loadMessages('chat-active', makeActions());

    const probeOrder =
      apiRequestMock.mock.invocationCallOrder[
        apiRequestMock.mock.calls.findIndex(([endpoint]) => endpoint === ACTIVE_SESSIONS_ENDPOINT)
      ];
    expect(probeOrder).toBeLessThan(getMessagesMock.mock.invocationCallOrder[0]);
  });

  it('still attaches when the run ends right after the messages were read', async () => {
    setupStore('chat-active');
    lastMessageIs('assistant');
    // The server answers "running" until the messages are read and "idle" for every later ask: a probe sent after the
    // messages would find nothing, and the page would keep the stored messages from before the run ended.
    apiRequestMock.mockImplementation(async (endpoint: string) =>
      endpoint === ACTIVE_SESSIONS_ENDPOINT
        ? { activeSessions: getMessagesMock.mock.calls.length === 0 ? [{ chatId: 'chat-active' }] : [] }
        : { active: false },
    );

    await loadMessages('chat-active', makeActions());

    await vi.waitFor(() => {
      expect(attachToChatMock).toHaveBeenCalledTimes(1);
    });
  });

  it('attaches after a user message without needing the server to report the chat as running', async () => {
    setupStore('chat-active');
    lastMessageIs('user');
    serverReports([]);

    await loadMessages('chat-active', makeActions());

    await vi.waitFor(() => {
      expect(attachToChatMock).toHaveBeenCalledTimes(1);
    });
  });

  it.each([
    ['skipActiveTurnAttach', { skipActiveTurnAttach: true }],
    ['preserveInstantSessionConfig', { preserveInstantSessionConfig: true }],
  ])('does not ask the server whether the chat runs when %s is set', async (_name, options) => {
    setupStore('chat-active');
    lastMessageIs('assistant');
    serverReports(['chat-active'], ['chat-active']);

    await loadMessages('chat-active', makeActions(), options);
    await settleRecovery();

    expect(activeSessionProbes()).toHaveLength(0);
    expect(attachToChatMock).not.toHaveBeenCalled();
    expect(attachForHitlRecoveryMock).not.toHaveBeenCalled();
  });

  it('does not attach when the user moved to another chat while the probe was in flight', async () => {
    setupStore('chat-active');
    lastMessageIs('assistant');
    let answerProbe: (sessions: { activeSessions: Array<{ chatId: string }> }) => void = () => {};
    apiRequestMock.mockImplementation(async (endpoint: string) => {
      if (endpoint !== ACTIVE_SESSIONS_ENDPOINT) {
        return { active: false };
      }
      return new Promise((resolve) => {
        answerProbe = resolve;
      });
    });

    await loadMessages('chat-active', makeActions());
    await vi.waitFor(() => {
      expect(activeSessionProbes()).toHaveLength(1);
    });
    mockStore.chatId = 'chat-other';
    answerProbe({ activeSessions: [{ chatId: 'chat-active' }] });
    await settleRecovery();

    expect(attachToChatMock).not.toHaveBeenCalled();
  });

  it('does not attach when the user started a turn while the probe was in flight', async () => {
    setupStore('chat-active');
    lastMessageIs('assistant');
    let answerProbe: (sessions: { activeSessions: Array<{ chatId: string }> }) => void = () => {};
    apiRequestMock.mockImplementation(async (endpoint: string) => {
      if (endpoint !== ACTIVE_SESSIONS_ENDPOINT) {
        return { active: false };
      }
      return new Promise((resolve) => {
        answerProbe = resolve;
      });
    });

    await loadMessages('chat-active', makeActions());
    await vi.waitFor(() => {
      expect(activeSessionProbes()).toHaveLength(1);
    });
    mockStore.loading = true;
    answerProbe({ activeSessions: [{ chatId: 'chat-active' }] });
    await settleRecovery();

    expect(attachToChatMock).not.toHaveBeenCalled();
  });

  it('brings the approval card back, without attaching to a turn, when the chat is parked behind a tool approval', async () => {
    setupStore('chat-active');
    lastMessageIs('assistant');
    serverReports([], ['chat-active']);

    await loadMessages('chat-active', makeActions());

    await vi.waitFor(() => {
      expect(attachForHitlRecoveryMock).toHaveBeenCalledTimes(1);
    });
    expect(attachForHitlRecoveryMock).toHaveBeenCalledWith('chat-active', expect.anything(), expect.any(Function));
    // A parked turn has no stream to follow: an attach would never end and the page would stay on "loading".
    expect(attachToChatMock).not.toHaveBeenCalled();
    expect(getMessagesMock).toHaveBeenCalledTimes(1);
    expect(mockStore.loading).toBe(false);
  });

  it('follows the running turn when the chat is both running and listed as awaiting', async () => {
    setupStore('chat-active');
    lastMessageIs('assistant');
    serverReports(['chat-active'], ['chat-active']);

    await loadMessages('chat-active', makeActions());

    await vi.waitFor(() => {
      expect(attachToChatMock).toHaveBeenCalledTimes(1);
    });
    expect(attachForHitlRecoveryMock).not.toHaveBeenCalled();
  });

  it('does not bring a card back for a chat other than the one loaded', async () => {
    setupStore('chat-active');
    lastMessageIs('assistant');
    serverReports([], ['chat-other']);

    await loadMessages('chat-active', makeActions());
    await vi.waitFor(() => {
      expect(activeSessionProbes()).toHaveLength(1);
    });
    await settleRecovery();

    expect(attachForHitlRecoveryMock).not.toHaveBeenCalled();
    expect(attachToChatMock).not.toHaveBeenCalled();
  });

  it('does not bring a card back when the user started a turn while the probe was in flight', async () => {
    setupStore('chat-active');
    lastMessageIs('assistant');
    let answerProbe: (sessions: { activeSessions: never[]; awaitingApprovalChatIds: string[] }) => void = () => {};
    apiRequestMock.mockImplementation(async (endpoint: string) => {
      if (endpoint !== ACTIVE_SESSIONS_ENDPOINT) {
        return { active: false };
      }
      return new Promise((resolve) => {
        answerProbe = resolve;
      });
    });

    await loadMessages('chat-active', makeActions());
    await vi.waitFor(() => {
      expect(activeSessionProbes()).toHaveLength(1);
    });
    mockStore.loading = true;
    answerProbe({ activeSessions: [], awaitingApprovalChatIds: ['chat-active'] });
    await settleRecovery();

    expect(attachForHitlRecoveryMock).not.toHaveBeenCalled();
  });

  it('keeps the load and later recoveries working when bringing the card back fails', async () => {
    setupStore('chat-active');
    lastMessageIs('assistant');
    serverReports([], ['chat-active']);
    attachForHitlRecoveryMock.mockRejectedValueOnce(new Error('attach failed'));

    await expect(loadMessages('chat-active', makeActions())).resolves.toBeUndefined();
    await vi.waitFor(() => {
      expect(attachForHitlRecoveryMock).toHaveBeenCalledTimes(1);
    });
    await settleRecovery();
    expect(mockStore.isMessagesLoaded).toBe(true);

    // The failed recovery must not leave the chat marked as "recovery in flight".
    await loadMessages('chat-active', makeActions());
    await vi.waitFor(() => {
      expect(attachForHitlRecoveryMock).toHaveBeenCalledTimes(2);
    });
  });

  it('refetches final messages when attach returns false (agent already finished)', async () => {
    setupStore('chat-active');
    getMessagesMock.mockResolvedValue({
      messages: [
        {
          messageId: 'msg-user',
          chatId: 'chat-active',
          createdAt: new Date('2026-08-08T00:00:00.000Z'),
          role: 'user',
          content: '只回复 OK',
        } as unknown as Message,
      ],
      has_more: false,
      next_cursor: null,
    });
    attachToChatMock.mockResolvedValue(false);

    await loadMessages('chat-active', makeActions());

    // First fetch, then one refetch after attach 404, and the refetch must not re-attach.
    await vi.waitFor(() => {
      expect(getMessagesMock).toHaveBeenCalledTimes(2);
    });
    expect(attachToChatMock).toHaveBeenCalledTimes(1);
  });

  it('skips attach when skipActiveTurnAttach is set (prevents recovery loops)', async () => {
    setupStore('chat-active');
    getMessagesMock.mockResolvedValue({
      messages: [
        {
          messageId: 'msg-user',
          chatId: 'chat-active',
          createdAt: new Date('2026-08-08T00:00:00.000Z'),
          role: 'user',
          content: 'hi',
        } as unknown as Message,
      ],
      has_more: false,
      next_cursor: null,
    });

    await loadMessages('chat-active', makeActions(), { skipActiveTurnAttach: true });

    expect(attachToChatMock).not.toHaveBeenCalled();
    expect(getMessagesMock).toHaveBeenCalledTimes(1);
  });

  it('does not attach for instant-session config-preserving loads', async () => {
    setupStore('chat-active');
    getMessagesMock.mockResolvedValue({
      messages: [
        {
          messageId: 'msg-user',
          chatId: 'chat-active',
          createdAt: new Date('2026-08-08T00:00:00.000Z'),
          role: 'user',
          content: 'hi',
        } as unknown as Message,
      ],
      has_more: false,
      next_cursor: null,
    });
    getChatDetailMock.mockResolvedValue({
      chat: {
        ...chatDetailPayload().chat,
        agent_id: 'agent-from-db',
      },
    });

    await loadMessages('chat-active', makeActions(), { preserveInstantSessionConfig: true });

    expect(attachToChatMock).not.toHaveBeenCalled();
    expect(restoreAgentConfigFromChatMock).toHaveBeenCalledWith('chat-active', 'agent-from-db');
  });

  it('defers isMessagesLoaded until restore completes when chat has agent_id', async () => {
    setupStore('chat-active');
    let loadedBeforeRestore = false;
    restoreAgentConfigFromChatMock.mockImplementation(async () => {
      loadedBeforeRestore = mockStore.isMessagesLoaded === true;
    });
    getChatDetailMock.mockResolvedValue({
      chat: {
        ...chatDetailPayload().chat,
        agent_id: 'agent-from-db',
      },
    });
    getMessagesMock.mockResolvedValue({
      messages: [],
      has_more: false,
      next_cursor: null,
    });

    await loadMessages('chat-active', makeActions());

    expect(loadedBeforeRestore).toBe(false);
    expect(mockStore.isMessagesLoaded).toBe(true);
    expect(mockStore.loading).toBe(false);
    expect(restoreAgentConfigFromChatMock).toHaveBeenCalledWith('chat-active', 'agent-from-db');
  });
});
