import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatState, Message } from '@/store/chat/types';
import { loadMessages } from '@/store/chat/messageManagement';

const getChatDetailMock = vi.hoisted(() => vi.fn());
const getMessagesMock = vi.hoisted(() => vi.fn());
const setAgentConfigMock = vi.hoisted(() => vi.fn());
const setSandboxModeMock = vi.hoisted(() => vi.fn());
const setContextPinnedFilesMock = vi.hoisted(() => vi.fn());
const setContextPinnedFilesLoadErrorMock = vi.hoisted(() => vi.fn());
const setContextBranchesMock = vi.hoisted(() => vi.fn());
const setContextBranchesLoadErrorMock = vi.hoisted(() => vi.fn());

vi.mock('@/services/chat', () => ({
  getChatDetail: (...args: unknown[]) => getChatDetailMock(...args),
  getMessages: (...args: unknown[]) => getMessagesMock(...args),
  getContextPins: vi.fn().mockResolvedValue({ files: [] }),
  listContextBranches: vi.fn().mockResolvedValue([]),
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
      chatId: 'chat-ttsr',
      agentConfig: null,
      messages: [],
      loading: false,
      isMessagesLoaded: false,
      abortController: null,
      setAgentConfig: setAgentConfigMock,
      setSandboxMode: setSandboxModeMock,
      setContextPinnedFiles: setContextPinnedFilesMock,
      setContextPinnedFilesLoadError: setContextPinnedFilesLoadErrorMock,
      setContextBranches: setContextBranchesMock,
      setContextBranchesLoadError: setContextBranchesLoadErrorMock,
      fetchTurnOutlines: vi.fn().mockResolvedValue(undefined),
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

describe('loadMessages ttsrInterventions persistence restore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getChatDetailMock.mockResolvedValue({
      chat: {
        id: 'chat-ttsr',
        title: 'TTSR Persistence Test',
        actionMode: 'agent',
        compacted_summary: null,
        compacted_before_id: null,
        workspace_dir: null,
        session_loaded_skill_names: null,
        is_incognito: false,
        agent_id: null,
        meta: {
          agent_config: null,
          sandbox_mode: false,
        },
      },
    });
  });

  it('restores ttsrInterventions from persisted metadata payload', async () => {
    getMessagesMock.mockResolvedValue({
      messages: [
        {
          messageId: 'msg-ttsr-1',
          chatId: 'chat-ttsr',
          createdAt: new Date('2026-09-27T00:00:00.000Z'),
          role: 'assistant',
          content: 'Safe answer after interception.',
          metadata: {
            ttsrInterventions: [
              {
                ruleId: 'rule_block_rm_rf',
                ruleName: 'Destructive Command Defense',
                reminder: 'rm -rf is dangerous',
                target: 'assistant',
                retryCount: 1,
                maxRetries: 2,
              },
            ],
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

    await loadMessages('chat-ttsr', actions);

    expect(state.messages).toHaveLength(1);
    const msg = state.messages[0];
    expect(msg?.ttsrInterventions).toBeDefined();
    expect(msg?.ttsrInterventions).toHaveLength(1);
    expect(msg?.ttsrInterventions?.[0]).toEqual({
      ruleId: 'rule_block_rm_rf',
      ruleName: 'Destructive Command Defense',
      reminder: 'rm -rf is dangerous',
      target: 'assistant',
      retryCount: 1,
      maxRetries: 2,
      timestamp: undefined,
    });
  });

  it('normalizes legacy snake_case ttsr_interventions correctly', async () => {
    getMessagesMock.mockResolvedValue({
      messages: [
        {
          messageId: 'msg-ttsr-2',
          chatId: 'chat-ttsr',
          createdAt: new Date('2026-09-27T00:00:00.000Z'),
          role: 'assistant',
          content: 'Output with snake_case metadata.',
          metadata: {
            ttsr_interventions: [
              {
                rule_id: 'rule_private_key',
                rule_name: 'Private Key Filter',
                reminder: 'Redact private keys',
                target: 'thinking',
                retry_count: 2,
                max_retries: 3,
              },
            ],
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

    await loadMessages('chat-ttsr', actions);

    expect(state.messages).toHaveLength(1);
    const msg = state.messages[0];
    expect(msg?.ttsrInterventions).toBeDefined();
    expect(msg?.ttsrInterventions).toHaveLength(1);
    expect(msg?.ttsrInterventions?.[0]).toEqual({
      ruleId: 'rule_private_key',
      ruleName: 'Private Key Filter',
      reminder: 'Redact private keys',
      target: 'thinking',
      retryCount: 2,
      maxRetries: 3,
      timestamp: undefined,
    });
  });
});
