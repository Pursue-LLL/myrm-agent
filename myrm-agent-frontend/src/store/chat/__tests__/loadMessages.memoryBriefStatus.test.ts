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
      chatId: 'chat-memory-brief',
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

describe('loadMessages memoryBriefStatus hydration', () => {
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
    getMessagesMock.mockResolvedValue({
      messages: [
        {
          messageId: 'msg-1',
          chatId: 'chat-memory-brief',
          createdAt: new Date('2026-07-18T00:00:00.000Z'),
          role: 'assistant',
          content: 'done',
          metadata: JSON.stringify({
            memoryBriefStatus: {
              state: 'skipped',
              reason: 'timeout',
              injection: { state: 'applied', source: 'fallback' },
            },
          }),
        } as unknown as Message,
      ],
      has_more: false,
      next_cursor: null,
    });
  });

  it('restores persisted memoryBriefStatus.injection from metadata payload', async () => {
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

    await loadMessages('chat-memory-brief', actions);

    expect(state.messages).toHaveLength(1);
    expect(state.messages[0]?.memoryBriefStatus).toEqual({
      state: 'skipped',
      reason: 'timeout',
      injection: { state: 'applied', source: 'fallback' },
    });
  });
});
