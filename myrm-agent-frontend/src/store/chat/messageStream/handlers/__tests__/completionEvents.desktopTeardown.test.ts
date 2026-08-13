/**
 * Tests that completionEvents releases desktop + browser inspector turn engagement on MESSAGE_END.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockDesktopReleaseTurnEngagement = vi.fn();
const mockBrowserReleaseTurnEngagement = vi.fn();

vi.mock('@/store/useDesktopInspectorStore', () => ({
  default: {
    getState: () => ({ releaseTurnEngagement: mockDesktopReleaseTurnEngagement }),
  },
}));

vi.mock('@/store/useBrowserInspectorStore', () => ({
  default: {
    getState: () => ({ releaseTurnEngagement: mockBrowserReleaseTurnEngagement }),
  },
}));

vi.mock('@/store/chat/goals/usePlanStore', () => ({
  usePlanStore: { getState: () => ({ clearActivePlan: vi.fn() }) },
}));

vi.mock('@/store/chat/goals/useGoalStore', () => ({
  useGoalStore: { getState: () => ({ setActiveGoal: vi.fn() }) },
}));

vi.mock('@/services/notification', () => ({
  notificationService: { notify: vi.fn() },
}));

vi.mock('@/lib/utils/completionSound', () => ({
  playCompletionSound: vi.fn(() => false),
  dispatchPetSurfaceAwayCompletion: vi.fn(),
}));

vi.mock('@/services/chat', () => ({
  getChatDetail: vi.fn(async () => ({ chat: {} })),
}));

vi.mock('@/lib/progression/tryMarkMilestone', () => ({
  tryMarkMilestone: vi.fn(),
}));

vi.mock('../handlerDeps', () => ({
  AgentEventType: {
    GOAL_STATUS: 'goal_status',
    FILE_MUTATION_FAILED: 'file_mutation_failed',
    MESSAGE_END: 'message_end',
  },
  findAssistantMessageIndex: vi.fn(() => 0),
  normalizeGoalState: vi.fn((payload: { status?: string }) => ({ status: payload?.status ?? 'active' })),
  releaseInspectorControls: (chatId: string) => {
    void import('@/lib/inspector/releaseTurnInspectorControls').then(({ releaseTurnInspectorControls }) =>
      releaseTurnInspectorControls(chatId),
    );
  },
  useChatStore: {
    getState: vi.fn(() => ({ chatId: 'c1', setWorkspaceDir: vi.fn() })),
  },
  useConfigStore: {
    getState: () => ({ enableCompletionSound: false, enableWebNotifications: false }),
  },
  useToolApprovalStore: {
    getState: vi.fn(() => ({ unmarkProcessing: vi.fn() })),
  },
  playCompletionSound: vi.fn(() => false),
  dispatchPetSurfaceAwayCompletion: vi.fn(),
}));

import { completionEvents } from '../completionEvents';
import type { StreamCtx } from '../../streamContext';

function makeCtx(): StreamCtx {
  return {
    data: { type: 'message_end', messageId: 'msg-1' } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: 'done',
    state: {
      messages: [{ messageId: 'msg-1', chatId: 'c1', role: 'assistant', content: '', createdAt: new Date() }],
      messageAppeared: false,
      loading: true,
    } as never,
    actions: {
      setMessages: vi.fn((updater: (s: Record<string, unknown>) => void) => updater({
        messages: [{ messageId: 'msg-1', chatId: 'c1', role: 'assistant', content: '', createdAt: new Date() }],
        loading: true,
        messageAppeared: false,
      })),
      setLoading: vi.fn(),
      setMessageAppeared: vi.fn(),
      _processSuggestions: vi.fn(),
      scheduleAutoSave: vi.fn(),
    } as never,
    files: [],
  };
}

describe('completionEvents inspector teardown', () => {
  beforeEach(() => {
    mockDesktopReleaseTurnEngagement.mockClear();
    mockBrowserReleaseTurnEngagement.mockClear();
  });

  it('releases desktop and browser turn engagement on MESSAGE_END', async () => {
    const ctx = makeCtx();
    await completionEvents(ctx);

    await vi.waitFor(() => {
      expect(mockDesktopReleaseTurnEngagement).toHaveBeenCalledTimes(1);
      expect(mockDesktopReleaseTurnEngagement).toHaveBeenCalledWith('c1');
      expect(mockBrowserReleaseTurnEngagement).toHaveBeenCalledTimes(1);
      expect(mockBrowserReleaseTurnEngagement).toHaveBeenCalledWith('c1');
    });
  });

  it('does not release inspector turn engagement for non-MESSAGE_END events', async () => {
    const ctx = makeCtx();
    ctx.data = { type: 'goal_status', data: {} } as never;
    await completionEvents(ctx);
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(mockDesktopReleaseTurnEngagement).not.toHaveBeenCalled();
    expect(mockBrowserReleaseTurnEngagement).not.toHaveBeenCalled();
  });

  it('releases desktop and browser turn engagement when a goal becomes budget_limited', async () => {
    const ctx = makeCtx();
    ctx.data = { type: 'goal_status', data: { status: 'budget_limited' } } as never;
    await completionEvents(ctx);

    await vi.waitFor(() => {
      expect(mockDesktopReleaseTurnEngagement).toHaveBeenCalledTimes(1);
      expect(mockDesktopReleaseTurnEngagement).toHaveBeenCalledWith('c1');
      expect(mockBrowserReleaseTurnEngagement).toHaveBeenCalledTimes(1);
      expect(mockBrowserReleaseTurnEngagement).toHaveBeenCalledWith('c1');
    });
  });
});
