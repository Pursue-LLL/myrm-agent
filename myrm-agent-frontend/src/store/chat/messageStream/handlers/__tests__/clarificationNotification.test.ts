/**
 * Tests for what the toolsProgressEvents handler raises on CLARIFICATION_REQUIRED: the card with the pause it answers,
 * and the OS notification.
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
}));

vi.mock('../handlerDeps', () => ({
  AgentEventType: {
    TOOL_HEARTBEAT: 'tool_heartbeat',
    TASKS_STEPS: 'tasks_steps',
    SOURCES: 'sources',
    APPROVAL_REQUIRED: 'approval_required',
    CLARIFICATION_REQUIRED: 'clarification_required',
    TOOL_APPROVAL_REQUEST: 'tool_approval_request',
    TOOLS_SNAPSHOT: 'tools_snapshot',
  },
  findAssistantMessageIndex: vi.fn(() => 0),
  resolveStreamChatId: vi.fn(() => 'c1'),
  useChatStore: {
    getState: vi.fn(() => ({ chatId: 'c1', actionMode: 'auto', addEnvironmentAlert: vi.fn() })),
  },
  useConfigStore: {
    getState: () => mockState,
  },
  useToolApprovalStore: {
    getState: vi.fn(() => ({
      addRequest: vi.fn(),
      queue: [],
    })),
  },
  useToolsSnapshotStore: {
    getState: vi.fn(() => ({ setTools: vi.fn() })),
  },
  mapTaskStepStatus: vi.fn(() => 'success'),
  mergeMessageSources: vi.fn(),
}));

import { findAssistantMessageIndex } from '../handlerDeps';
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
      messages: [{ messageId: 'msg-1', chatId: 'c1', role: 'assistant', content: '', createdAt: new Date() }],
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
    expect(mockNotify).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ fallbackToToast: false }));
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
    const draft: {
      messages: Array<{
        messageId?: string;
        chatId?: string;
        role?: 'assistant';
        content?: string;
        clarification?: { answered?: boolean; form?: { questions?: Array<{ id: string }> } };
      }>;
    } = {
      messages: [
        {
          messageId: 'msg-1',
          chatId: 'c1',
          role: 'assistant' as const,
          content: '',
          clarification: { answered: false, form: { questions: [] } },
        },
      ],
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

    expect(mockNotify).toHaveBeenCalledWith('Agent 需要您的输入', expect.objectContaining({ fallbackToToast: false }));

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

type CardRow = { clarification?: { answered: boolean; interruptId?: string } };

/** Runs the handler for one announced card and applies its store update to a draft holding `rows`. */
async function announceCard(extra: Record<string, unknown>, rows: CardRow[]): Promise<CardRow[]> {
  const setMessages = vi.fn();
  const ctx = makeCtx('clarification_required', { data: productionClarifyData, ...extra });
  ctx.actions.setMessages = setMessages;
  await toolsProgressEvents(ctx);
  const apply = setMessages.mock.calls[0]?.[0] as (draft: { messages: CardRow[] }) => void;
  const draft = { messages: rows };
  apply(draft);
  return draft.messages;
}

describe('toolsProgressEvents clarification card address', () => {
  // The answer is addressed to the pause that asked, so the card has to remember which pause that was.
  it('keeps the interrupt id the card was announced with', async () => {
    const [row] = await announceCard({ interruptId: 'int-1' }, [{}]);

    expect(row.clarification).toMatchObject({ answered: false, interruptId: 'int-1' });
  });

  it('keeps it on the row the card creates when the stream has none yet', async () => {
    vi.mocked(findAssistantMessageIndex).mockReturnValueOnce(-1);

    const [row] = await announceCard({ interruptId: 'int-1' }, []);

    expect(row.clarification?.interruptId).toBe('int-1');
  });

  it('replaces the id of an earlier card on the same row with the id of the new pause', async () => {
    const [row] = await announceCard({ interruptId: 'int-2' }, [
      { clarification: { answered: true, interruptId: 'int-1' } },
    ]);

    expect(row.clarification).toMatchObject({ answered: false, interruptId: 'int-2' });
  });

  it('leaves the card without an id when the pause was announced without one', async () => {
    const [row] = await announceCard({}, [{}]);

    expect(row.clarification?.interruptId).toBeUndefined();
  });
});
