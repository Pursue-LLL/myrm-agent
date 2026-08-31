import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatState, Message } from '@/store/chat/types';
import { loadMessages } from '@/store/chat/messageManagement';

const getChatDetailMock = vi.hoisted(() => vi.fn());
const getMessagesMock = vi.hoisted(() => vi.fn());
const attachToChatMock = vi.hoisted(() => vi.fn());
const restoreAgentConfigFromChatMock = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));

const mockStore = vi.hoisted(() => {
  const store: Record<string, unknown> = {
    chatId: 'chat-active',
    messages: [] as unknown[],
    loading: false,
    abortController: null,
    setContextPinnedFiles: vi.fn(),
    setContextPinnedFilesLoadError: vi.fn(),
    setContextBranches: vi.fn(),
    setContextBranchesLoadError: vi.fn(),
    setSandboxMode: vi.fn(),
    setAgentConfig: vi.fn(),
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
  apiRequest: vi.fn().mockResolvedValue({ active: false }),
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
  attachForHitlRecovery: vi.fn(),
}));

vi.mock('@/store/chat/chatAgentSessionRestore', () => ({
  restoreAgentConfigFromChat: (...args: unknown[]) => restoreAgentConfigFromChatMock(...args),
}));

function setupStore(chatId: string): void {
  mockStore.chatId = chatId;
  mockStore.messages = [];
  mockStore.loading = false;
  mockStore.abortController = null;
}

function makeActions(): Parameters<typeof loadMessages>[1] {
  return {
    setMessages: (updater: (draft: ChatState) => void) => updater(mockStore as unknown as ChatState),
  } as unknown as Parameters<typeof loadMessages>[1];
}

function chatDetailPayload(): Record<string, unknown> {
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

describe('loadMessages active-turn SSE recovery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getChatDetailMock.mockResolvedValue(chatDetailPayload());
    attachToChatMock.mockResolvedValue(true);
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
});
