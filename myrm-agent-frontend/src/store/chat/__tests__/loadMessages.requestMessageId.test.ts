import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatState, Message } from '@/store/chat/types';
import { loadMessages } from '@/store/chat/messageManagement';

const getChatDetailMock = vi.hoisted(() => vi.fn());
const getMessagesMock = vi.hoisted(() => vi.fn());
const setAgentConfigMock = vi.hoisted(() => vi.fn());
const setSandboxModeMock = vi.hoisted(() => vi.fn());

vi.mock('@/services/chat', () => ({
  getChatDetail: (...args: unknown[]) => getChatDetailMock(...args),
  getMessages: (...args: unknown[]) => getMessagesMock(...args),
  generateChatTitle: vi.fn(),
  updateChatTitle: vi.fn(),
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
    getState: () => ({
      chatId: 'chat-rid',
      agentConfig: null,
      setAgentConfig: setAgentConfigMock,
      setSandboxMode: setSandboxModeMock,
    }),
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

describe('loadMessages requestMessageId hydration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
  });

  it('restores requestMessageId from metadata.request_message_id for assistant messages', async () => {
    getMessagesMock.mockResolvedValue({
      messages: [
        {
          messageId: 'db-uuid-assistant-1',
          chatId: 'chat-rid',
          createdAt: new Date('2026-08-13T00:00:00.000Z'),
          role: 'user',
          content: 'U1',
        },
        {
          messageId: 'db-uuid-assistant-2',
          chatId: 'chat-rid',
          createdAt: new Date('2026-08-13T00:00:01.000Z'),
          role: 'assistant',
          content: 'A1',
          metadata: { request_message_id: 'r-abc123' },
        } as unknown as Message,
      ],
      has_more: false,
      next_cursor: null,
    });

    const state = {
      chatId: '',
      messages: [],
      loading: false,
      isMessagesLoaded: false,
      notFound: false,
      loadError: false,
      actionMode: 'agent',
      compactedSummary: null,
      compactedBeforeId: null,
      workspaceDir: null,
      sessionSkillOverrides: null,
      incognitoMode: false,
      hasMoreMessages: false,
      nextCursor: null,
    } as unknown as ChatState;

    const actions = {
      setMessages: (updater: (draft: ChatState) => void) => updater(state),
    } as unknown as Parameters<typeof loadMessages>[1];

    await loadMessages('chat-rid', actions);

    expect(state.messages).toHaveLength(2);
    const assistant = state.messages.find((m) => m.role === 'assistant');
    expect(assistant?.messageId).toBe('db-uuid-assistant-2');
    expect(assistant?.requestMessageId).toBe('r-abc123');
  });

  it('leaves requestMessageId undefined when metadata lacks request_message_id', async () => {
    getMessagesMock.mockResolvedValue({
      messages: [
        {
          messageId: 'r-user-1',
          chatId: 'chat-rid',
          createdAt: new Date('2026-08-13T00:00:00.000Z'),
          role: 'user',
          content: 'U1',
        } as unknown as Message,
      ],
      has_more: false,
      next_cursor: null,
    });

    const state = {
      chatId: '',
      messages: [],
      loading: false,
      isMessagesLoaded: false,
      notFound: false,
      loadError: false,
      actionMode: 'agent',
      compactedSummary: null,
      compactedBeforeId: null,
      workspaceDir: null,
      sessionSkillOverrides: null,
      incognitoMode: false,
      hasMoreMessages: false,
      nextCursor: null,
    } as unknown as ChatState;

    const actions = {
      setMessages: (updater: (draft: ChatState) => void) => updater(state),
    } as unknown as Parameters<typeof loadMessages>[1];

    await loadMessages('chat-rid', actions);

    expect(state.messages).toHaveLength(1);
    expect(state.messages[0]?.messageId).toBe('r-user-1');
    expect(state.messages[0]?.requestMessageId).toBeUndefined();
  });
});
