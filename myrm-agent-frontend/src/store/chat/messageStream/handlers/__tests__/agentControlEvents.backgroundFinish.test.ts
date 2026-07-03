/**
 * Background finish ptc_notify must not toast — server SYSTEM_NOTIFICATION is canonical.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();
const mockNotifyBackgroundTasksChanged = vi.fn();

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    error: (...args: unknown[]) => mockToastError(...args),
    warning: vi.fn(),
    success: (...args: unknown[]) => mockToastSuccess(...args),
  },
}));

vi.mock('@/services/backgroundTasksRefresh', () => ({
  notifyBackgroundTasksChanged: () => mockNotifyBackgroundTasksChanged(),
}));

vi.mock('../handlerDeps', () => ({
  AgentEventType: {
    PTC_NOTIFY: 'ptc_notify',
  },
  findAssistantMessageIndex: vi.fn(() => 0),
  getUserFriendlyError: vi.fn(),
  useChatStore: { getState: vi.fn(() => ({ chatId: 'c1' })) },
  useToolApprovalStore: { getState: vi.fn(() => ({ unmarkProcessing: vi.fn() })) },
  getContextOverflowMessage: vi.fn(),
}));

import { agentControlEvents } from '../agentControlEvents';
import type { StreamCtx } from '../../streamContext';

function makePtcCtx(extra: Record<string, unknown> = {}): StreamCtx {
  return {
    data: {
      type: 'ptc_notify',
      messageId: 'msg-1',
      data: {
        message: 'Background job pid=42 exited (exit_code=0)',
        level: 'info',
        progress: 100,
        category: 'background:42',
        ...extra,
      },
    } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: '',
    state: {
      messages: [
        {
          messageId: 'msg-1',
          chatId: 'c1',
          role: 'assistant',
          content: '',
          createdAt: new Date(),
          progressSteps: [],
        },
      ],
      messageAppeared: false,
      loading: false,
    } as never,
    actions: {
      setMessages: vi.fn((updater: (s: Record<string, unknown>) => void) =>
        updater({
          messages: [
            {
              messageId: 'msg-1',
              chatId: 'c1',
              role: 'assistant',
              content: '',
              createdAt: new Date(),
              progressSteps: [],
            },
          ],
          loading: false,
          messageAppeared: false,
        }),
      ),
      setLoading: vi.fn(),
    } as never,
    files: [],
  };
}

describe('agentControlEvents background finish', () => {
  beforeEach(() => {
    mockToastSuccess.mockClear();
    mockToastError.mockClear();
    mockNotifyBackgroundTasksChanged.mockClear();
  });

  it('does not toast on background finish progress=100 (server notification is canonical)', async () => {
    const ctx = makePtcCtx();
    await agentControlEvents(ctx);
    expect(mockToastSuccess).not.toHaveBeenCalled();
    expect(mockNotifyBackgroundTasksChanged).toHaveBeenCalled();
  });

  it('still toasts alert-level background errors', async () => {
    const ctx = makePtcCtx({
      level: 'alert',
      error_category: 'oom_killed',
      message: 'Background job pid=42 oom_killed',
    });
    await agentControlEvents(ctx);
    expect(mockToastSuccess).not.toHaveBeenCalled();
    expect(mockToastError).toHaveBeenCalled();
  });
});
