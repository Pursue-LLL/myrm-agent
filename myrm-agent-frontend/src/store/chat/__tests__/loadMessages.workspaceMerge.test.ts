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
      chatId: 'chat-wsmr',
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

describe('loadMessages workspace merge hydration', () => {
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

  it('restores workspaceMergeFailures and counts from metadata payload', async () => {
    getMessagesMock.mockResolvedValue({
      messages: [
        {
          messageId: 'msg-wsmr',
          chatId: 'chat-wsmr',
          createdAt: new Date('2026-08-04T00:00:00.000Z'),
          role: 'assistant',
          content: 'Workspace merge E2E fixture answer.',
          metadata: {
            workspaceMergeFailures: [{ message: 'task_index=1: No space left on device' }],
            workspaceMergeFailedCount: 3,
            workspaceMergeTruncated: 2,
            completionStatus: 'warning',
          },
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

    await loadMessages('chat-wsmr', actions);

    expect(state.messages).toHaveLength(1);
    expect(state.messages[0]?.workspaceMergeFailures).toEqual([
      { message: 'task_index=1: No space left on device' },
    ]);
    expect(state.messages[0]?.workspaceMergeFailedCount).toBe(3);
    expect(state.messages[0]?.workspaceMergeTruncated).toBe(2);
    expect(state.messages[0]?.completionStatus).toBe('warning');
  });
});
