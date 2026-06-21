/**
 * Tests for OS notification dispatch on MESSAGE_END in completionEvents handler.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { mockNotify, mockState } = vi.hoisted(() => {
  return {
    mockNotify: vi.fn(),
    mockState: { enableCompletionSound: false, enableWebNotifications: true },
  };
});

vi.mock('@/services/notification', () => ({
  notificationService: { notify: mockNotify },
}));

vi.mock('@/lib/utils/completionSound', () => ({
  playCompletionSound: vi.fn(() => false),
}));

vi.mock('@/services/chat', () => ({
  getChatDetail: vi.fn(async () => ({ chat: {} })),
}));

vi.mock('../handlerDeps', () => ({
  AgentEventType: {
    CLIENT_ACTION: 'client_action',
    GOAL_STATUS: 'goal_status',
    FILE_MUTATION_FAILED: 'file_mutation_failed',
    MESSAGE_END: 'message_end',
  },
  findAssistantMessageIndex: vi.fn(() => 0),
  normalizeGoalState: vi.fn(),
  useChatStore: {
    getState: vi.fn(() => ({ chatId: 'c1', setWorkspaceDir: vi.fn() })),
  },
  useConfigStore: {
    getState: () => mockState,
  },
  useToolApprovalStore: {
    getState: vi.fn(() => ({ unmarkProcessing: vi.fn() })),
  },
  playCompletionSound: vi.fn(() => false),
}));

import { completionEvents } from '../completionEvents';
import type { StreamCtx } from '../../streamContext';

function makeCtx(): StreamCtx {
  return {
    data: { type: 'message_end', messageId: 'msg-1' } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: 'test response',
    state: {
      messages: [
        { messageId: 'msg-1', chatId: 'c1', role: 'assistant', content: '', createdAt: new Date() },
      ],
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

describe('completionEvents notification dispatch', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockNotify.mockClear();
    mockState.enableWebNotifications = true;
    mockState.enableCompletionSound = false;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('calls notificationService.notify on MESSAGE_END when enableWebNotifications=true', async () => {
    const ctx = makeCtx();
    await completionEvents(ctx);
    await vi.dynamicImportSettled();

    expect(mockNotify).toHaveBeenCalledTimes(1);
    expect(mockNotify).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ fallbackToToast: false }),
    );
  });

  it('does NOT call notificationService.notify when enableWebNotifications=false', async () => {
    mockState.enableWebNotifications = false;

    const ctx = makeCtx();
    await completionEvents(ctx);
    await vi.dynamicImportSettled();

    expect(mockNotify).not.toHaveBeenCalled();
  });

  it('uses Chinese title when document lang is zh', async () => {
    const origLang = document.documentElement.lang;
    document.documentElement.lang = 'zh-CN';

    const ctx = makeCtx();
    await completionEvents(ctx);
    await vi.dynamicImportSettled();

    expect(mockNotify).toHaveBeenCalledWith(
      'Agent 回复已完成',
      expect.objectContaining({ fallbackToToast: false }),
    );

    document.documentElement.lang = origLang;
  });

  it('uses English title when document lang is en', async () => {
    const origLang = document.documentElement.lang;
    document.documentElement.lang = 'en';

    const ctx = makeCtx();
    await completionEvents(ctx);
    await vi.dynamicImportSettled();

    expect(mockNotify).toHaveBeenCalledWith(
      'Agent response completed',
      expect.objectContaining({ fallbackToToast: false }),
    );

    document.documentElement.lang = origLang;
  });
});
