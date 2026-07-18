import { beforeEach, describe, expect, it, vi } from 'vitest';

import { resolveBriefUnavailableDescriptionKey } from '@/components/features/message-box/MemoryInsightPanel';
import { loadMessages } from '@/store/chat/messageManagement';
import type { ChatState, Message } from '@/store/chat/types';
import { completionEvents } from '../messageStream/handlers/completionEvents';
import type { StreamCtx } from '../messageStream/streamContext';

const getChatDetailMock = vi.hoisted(() => vi.fn());
const getMessagesMock = vi.hoisted(() => vi.fn());
const clearActivePlanMock = vi.hoisted(() => vi.fn());
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

vi.mock('@/services/notification', () => ({
  notificationService: { notify: vi.fn() },
}));

vi.mock('@/store/chat/goals/usePlanStore', () => ({
  usePlanStore: { getState: () => ({ clearActivePlan: clearActivePlanMock }) },
}));

vi.mock('@/store/chat/goals/useGoalStore', () => ({
  useGoalStore: { getState: () => ({ setActiveGoal: vi.fn() }) },
}));

vi.mock('@/store/useWorkspaceStore', () => ({
  default: {
    getState: () => ({ panes: [] }),
  },
}));

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => ({
      chatId: 'chat-flow',
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
  useConfigStore: {
    getState: () => ({ enableCompletionSound: false, enableWebNotifications: false }),
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

vi.mock('../messageStream/handlers/handlerDeps', () => ({
  AgentEventType: {
    GOAL_STATUS: 'goal_status',
    FILE_MUTATION_FAILED: 'file_mutation_failed',
    MESSAGE_END: 'message_end',
  },
  findAssistantMessageIndex: vi.fn(
    (messages: Array<{ messageId: string; role: string }>, messageId: string) =>
      messages.findIndex((msg) => msg.role === 'assistant' && msg.messageId === messageId)
  ),
  normalizeGoalState: vi.fn(),
  useChatStore: {
    getState: vi.fn(() => ({ chatId: 'chat-flow', setWorkspaceDir: vi.fn() })),
  },
  useConfigStore: {
    getState: () => ({ enableCompletionSound: false, enableWebNotifications: false }),
  },
  useToolApprovalStore: {
    getState: vi.fn(() => ({ unmarkProcessing: vi.fn() })),
  },
  playCompletionSound: vi.fn(() => false),
}));

type StreamState = {
  messages: Array<Record<string, unknown>>;
  messageAppeared: boolean;
  loading: boolean;
};

function makeMessageEndCtx(state: StreamState): StreamCtx {
  return {
    data: {
      type: 'message_end',
      messageId: 'assistant-1',
      memory_brief_status: {
        state: 'skipped',
        reason: 'timeout',
        source: 'preflight',
        injection: { state: 'not_applied', reason: 'recall_mode_tools' },
      },
    } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: 'done',
    state: state as never,
    actions: {
      setMessages: (updater: (draft: StreamState) => void) => updater(state),
      setLoading: vi.fn(),
      setMessageAppeared: vi.fn(),
      _processSuggestions: vi.fn(),
      scheduleAutoSave: vi.fn(),
    } as never,
    files: [],
  };
}

describe('memoryBriefStatus end-to-end flow', () => {
  beforeEach(() => {
    vi.useFakeTimers();
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

  it('keeps memory injection semantics from SSE through persistence and hydration to UI copy key', async () => {
    const streamState: StreamState = {
      messages: [
        {
          messageId: 'assistant-1',
          chatId: 'chat-flow',
          role: 'assistant',
          content: '',
          createdAt: new Date(),
        },
      ],
      messageAppeared: false,
      loading: true,
    };

    await completionEvents(makeMessageEndCtx(streamState));
    vi.runAllTimers();
    await vi.dynamicImportSettled();

    const streamedStatus = streamState.messages[0]?.memoryBriefStatus;
    expect(streamedStatus).toEqual({
      state: 'skipped',
      reason: 'timeout',
      source: 'preflight',
      injection: { state: 'not_applied', reason: 'recall_mode_tools' },
    });

    getMessagesMock.mockResolvedValue({
      messages: [
        {
          messageId: 'assistant-1',
          chatId: 'chat-flow',
          createdAt: new Date('2026-07-18T00:00:00.000Z'),
          role: 'assistant',
          content: 'done',
          metadata: JSON.stringify({
            memoryBriefStatus: streamedStatus,
          }),
        } as unknown as Message,
      ],
      has_more: false,
      next_cursor: null,
    });

    const chatState = {
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
      setMessages: (updater: (draft: ChatState) => void) => updater(chatState),
    } as unknown as Parameters<typeof loadMessages>[1];

    await loadMessages('chat-flow', actions);

    const hydratedStatus = chatState.messages[0]?.memoryBriefStatus;
    expect(hydratedStatus).toEqual(streamedStatus);
    expect(resolveBriefUnavailableDescriptionKey(hydratedStatus)).toBe(
      'briefUnavailableDescriptionToolsMode'
    );
  });
});

