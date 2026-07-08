/**
 * Tests for OS notification dispatch on CLARIFICATION_REQUIRED in toolsProgressEvents handler.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { mockNotify, mockState } = vi.hoisted(() => {
  return {
    mockNotify: vi.fn(),
    mockState: { enableWebNotifications: true },
  };
});

vi.mock('@/services/notification', () => ({
  notificationService: { notify: mockNotify },
}));

vi.mock('@/lib/approval/buildToolApprovalRequest', () => ({
  buildToolApprovalRequest: vi.fn(() => ({ id: 'mock-req' })),
}));

vi.mock('@/lib/approval/approvalAlertService', () => ({
  notifyIdleApproval: vi.fn(),
  clearAllNotifications: vi.fn(),
}));

vi.mock('../handlerDeps', () => ({
  AgentEventType: {
    TOOL_PROGRESS: 'tool_progress',
    TOOL_HEARTBEAT: 'tool_heartbeat',
    TASKS_STEPS: 'tasks_steps',
    SOURCES: 'sources',
    APPROVAL_REQUIRED: 'approval_required',
    CLARIFICATION_REQUIRED: 'clarification_required',
    TOOL_APPROVAL_REQUEST: 'tool_approval_request',
    APPROVAL_PROCESSED: 'approval_processed',
    TOOLS_SNAPSHOT: 'tools_snapshot',
    CORRECTION_LEARNED: 'correction_learned',
  },
  findAssistantMessageIndex: vi.fn(() => 0),
  useChatStore: {
    getState: vi.fn(() => ({ chatId: 'c1', actionMode: 'auto', addEnvironmentAlert: vi.fn() })),
  },
  useConfigStore: {
    getState: () => mockState,
  },
  useToolApprovalStore: {
    getState: vi.fn(() => ({
      addRequest: vi.fn(),
      removeRequestsByMessageId: vi.fn(),
      queue: [],
    })),
  },
  useToolsSnapshotStore: {
    getState: vi.fn(() => ({ setTools: vi.fn() })),
  },
  mapTaskStepStatus: vi.fn(() => 'success'),
  mergeMessageSources: vi.fn(),
}));

import { toolsProgressEvents } from '../toolsProgressEvents';
import type { StreamCtx } from '../../streamContext';

const productionClarifyData = {
  type: 'ask_question',
  form: {
    title: 'Which database?',
    questions: [
      {
        id: 'db',
        prompt: 'Pick a database',
        options: [
          { id: 'postgres', label: 'PostgreSQL' },
          { id: 'mysql', label: 'MySQL' },
        ],
      },
    ],
  },
};

function makeCtx(eventType: string, extra: Record<string, unknown> = {}): StreamCtx {
  return {
    data: { type: eventType, messageId: 'msg-1', ...extra } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: '',
    state: {
      messages: [
        { messageId: 'msg-1', chatId: 'c1', role: 'assistant', content: '', createdAt: new Date() },
      ],
    } as never,
    actions: {
      setLoading: vi.fn(),
      setMessages: vi.fn(),
    } as never,
    files: [],
  };
}

describe('toolsProgressEvents clarification notification', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockNotify.mockClear();
    mockState.enableWebNotifications = true;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('calls notificationService.notify on CLARIFICATION_REQUIRED when enableWebNotifications=true', async () => {
    const ctx = makeCtx('clarification_required', {
      data: productionClarifyData,
    });
    await toolsProgressEvents(ctx);
    await vi.dynamicImportSettled();

    expect(mockNotify).toHaveBeenCalledTimes(1);
    expect(mockNotify).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ fallbackToToast: false }),
    );
  });

  it('passes unwrapped form title as notification body', async () => {
    const ctx = makeCtx('clarification_required', {
      data: productionClarifyData,
    });
    await toolsProgressEvents(ctx);
    await vi.dynamicImportSettled();

    expect(mockNotify).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ body: 'Which database?', fallbackToToast: false }),
    );
  });

  it('stores normalized clarification form from production wire payload', async () => {
    const setMessages = vi.fn();
    const ctx = makeCtx('clarification_required', {
      data: productionClarifyData,
    });
    ctx.actions.setMessages = setMessages;

    await toolsProgressEvents(ctx);

    expect(setMessages).toHaveBeenCalled();
    const updater = setMessages.mock.calls[0]?.[0] as (state: {
      messages: Array<{ clarification?: { form?: { questions?: Array<{ id: string }> } } }>;
    }) => void;
    const draft = {
      messages: [{ messageId: 'msg-1', chatId: 'c1', role: 'assistant' as const, content: '' }],
    };
    updater(draft);
    expect(draft.messages[0]?.clarification?.form?.questions?.[0]?.id).toBe('db');
  });

  it('does NOT call notificationService.notify when enableWebNotifications=false', async () => {
    mockState.enableWebNotifications = false;

    const ctx = makeCtx('clarification_required', {
      data: productionClarifyData,
    });
    await toolsProgressEvents(ctx);
    await vi.dynamicImportSettled();

    expect(mockNotify).not.toHaveBeenCalled();
  });

  it('uses Chinese title when document lang starts with zh', async () => {
    const origLang = document.documentElement.lang;
    document.documentElement.lang = 'zh';

    const ctx = makeCtx('clarification_required', {
      data: productionClarifyData,
    });
    await toolsProgressEvents(ctx);
    await vi.dynamicImportSettled();

    expect(mockNotify).toHaveBeenCalledWith(
      'Agent 需要您的输入',
      expect.objectContaining({ fallbackToToast: false }),
    );

    document.documentElement.lang = origLang;
  });

  it('uses Japanese title when document lang starts with ja', async () => {
    const origLang = document.documentElement.lang;
    document.documentElement.lang = 'ja';

    const ctx = makeCtx('clarification_required', {
      data: productionClarifyData,
    });
    await toolsProgressEvents(ctx);
    await vi.dynamicImportSettled();

    expect(mockNotify).toHaveBeenCalledWith(
      'Agentがあなたの入力を必要としています',
      expect.objectContaining({ fallbackToToast: false }),
    );

    document.documentElement.lang = origLang;
  });

  it('handles missing form title gracefully', async () => {
    const ctx = makeCtx('clarification_required', {
      data: {
        type: 'ask_question',
        form: {
          questions: [
            {
              id: 'q1',
              prompt: 'Choose one',
              options: [{ id: 'a', label: 'A' }],
            },
          ],
        },
      },
    });
    await toolsProgressEvents(ctx);
    await vi.dynamicImportSettled();

    expect(mockNotify).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ body: undefined, fallbackToToast: false }),
    );
  });
});
