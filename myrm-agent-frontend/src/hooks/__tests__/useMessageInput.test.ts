import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockValidateMessageQuota = vi.hoisted(() => vi.fn(async () => ({ allowed: true })));
const mockRecordChatWikiQueryAttempt = vi.hoisted(() => vi.fn());
const mockRecordChatWikiQuerySubmitted = vi.hoisted(() => vi.fn());
const mockQueuePendingChatWikiQuerySuccess = vi.hoisted(() => vi.fn());
const mockSendMessage = vi.hoisted(() => vi.fn(async () => undefined));
const mockSteerMessage = vi.hoisted(() => vi.fn(async () => true));
const mockEnqueue = vi.hoisted(() => vi.fn());
const mockSetInputMessage = vi.hoisted(() => vi.fn());
const mockSetPendingArchiveRestoreActions = vi.hoisted(() => vi.fn());
const mockClearDraft = vi.hoisted(() => vi.fn());
const chatStoreRef = vi.hoisted(() => ({ state: {} as Record<string, unknown> }));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/hooks/billing/useQuotaGuard', () => ({
  useQuotaGuard: () => ({
    validateMessageQuota: (...args: unknown[]) => mockValidateMessageQuota(...args),
  }),
}));

vi.mock('@/hooks/shared/useDraftPersistence', () => ({
  useDraftPersistence: () => ({
    initialDraft: '',
    clearDraft: (...args: unknown[]) => mockClearDraft(...args),
  }),
}));

vi.mock('@/store/useChatStore', () => {
  const useChatStore = ((selector: (state: Record<string, unknown>) => unknown) =>
    selector(chatStoreRef.state)) as unknown as {
    (selector: (state: Record<string, unknown>) => unknown): unknown;
    getState: () => Record<string, unknown>;
  };
  useChatStore.getState = () => chatStoreRef.state;
  return { default: useChatStore };
});

vi.mock('@/hooks/message-input/useMessageQueue', () => ({
  useMessageQueue: () => ({
    queue: [],
    enqueue: (...args: unknown[]) => mockEnqueue(...args),
    dequeue: vi.fn(() => null),
    editMessage: vi.fn(),
    removeMessage: vi.fn(),
    clearQueue: vi.fn(),
    requeue: vi.fn(),
    reorder: vi.fn(),
  }),
}));

vi.mock('@/hooks/message-input/useInputFileUpload', () => ({
  useInputFileUpload: () => ({
    isUploadingPaste: false,
    handlePaste: vi.fn(),
    handleDroppedFiles: vi.fn(),
  }),
}));

vi.mock('@/store/useArtifactPortalStore', () => ({
  default: {
    getState: () => ({
      getDirtyArtifacts: () => ({}),
      clearDirtyState: vi.fn(),
    }),
  },
}));

vi.mock('@/store/chat/archiveRestoreActions', () => ({
  resolveArchiveRestoreActionsForMessage: vi.fn(() => undefined),
}));

vi.mock('@/hooks/message-input/useInputHistory', () => ({
  addInputHistory: vi.fn(),
}));

vi.mock('@/hooks/message-input/useMessageInputWikiEvidenceCore', () => ({
  recordChatWikiQueryAttempt: (...args: unknown[]) => mockRecordChatWikiQueryAttempt(...args),
  recordChatWikiQuerySubmitted: (...args: unknown[]) => mockRecordChatWikiQuerySubmitted(...args),
  queuePendingChatWikiQuerySuccess: (...args: unknown[]) => mockQueuePendingChatWikiQuerySuccess(...args),
}));

vi.mock('@/services/chat', () => ({
  compactChat: vi.fn(),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    info: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    loading: vi.fn(),
    success: vi.fn(),
  },
}));

function buildChatState(overrides: Partial<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    chatId: 'chat-test',
    sendMessage: (...args: unknown[]) => mockSendMessage(...args),
    steerMessage: (...args: unknown[]) => mockSteerMessage(...args),
    actionMode: 'agent',
    setActionMode: vi.fn(),
    files: [],
    setFiles: vi.fn(),
    hideAttachList: false,
    setHideAttachList: vi.fn(),
    stopMessage: vi.fn(),
    clearCurrentSessionMessageId: vi.fn(),
    getCurrentSessionMessageId: vi.fn(() => 'msg-live'),
    inputMessage: 'hello world',
    setInputMessage: (value: string) => {
      chatStoreRef.state.inputMessage = value;
      mockSetInputMessage(value);
    },
    pendingArchiveRestoreActions: [],
    setPendingArchiveRestoreActions: (actions: unknown[]) => {
      chatStoreRef.state.pendingArchiveRestoreActions = actions;
      mockSetPendingArchiveRestoreActions(actions);
    },
    loadMessages: vi.fn(async () => undefined),
    loading: false,
    messages: [],
    agentConfig: null,
    ...overrides,
  };
}

describe('useMessageInput submit telemetry integration', () => {
  beforeEach(() => {
    mockValidateMessageQuota.mockClear();
    mockRecordChatWikiQueryAttempt.mockClear();
    mockRecordChatWikiQuerySubmitted.mockClear();
    mockSendMessage.mockClear();
    mockSteerMessage.mockClear();
    mockEnqueue.mockClear();
    mockSetInputMessage.mockClear();
    mockSetPendingArchiveRestoreActions.mockClear();
    mockClearDraft.mockClear();
    mockQueuePendingChatWikiQuerySuccess.mockClear();
    chatStoreRef.state = buildChatState();
  });

  it('records query attempt and sends success-marked request on handleSubmit', async () => {
    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    await act(async () => {
      await result.current.handleSubmit();
    });

    expect(mockRecordChatWikiQueryAttempt).toHaveBeenCalledTimes(1);
    expect(mockSendMessage).toHaveBeenCalledWith(
      'hello world',
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      true,
    );
  });

  it('records query attempt and enqueues message on handleQueueSubmit', async () => {
    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    await act(async () => {
      await result.current.handleQueueSubmit();
    });

    expect(mockRecordChatWikiQueryAttempt).toHaveBeenCalledTimes(1);
    expect(mockEnqueue).toHaveBeenCalledWith('hello world', [], undefined);
  });

  it('records query attempt and falls back to sendMessage when steer fails', async () => {
    mockSteerMessage.mockResolvedValueOnce(false);
    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    await act(async () => {
      await result.current.handleSteerSubmit();
    });

    expect(mockRecordChatWikiQueryAttempt).toHaveBeenCalledTimes(1);
    expect(mockSendMessage).toHaveBeenCalledWith(
      'hello world',
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      true,
    );
  });

  it('queues pending query success when steer succeeds', async () => {
    mockSteerMessage.mockResolvedValueOnce(true);
    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    await act(async () => {
      await result.current.handleSteerSubmit();
    });

    expect(mockRecordChatWikiQueryAttempt).toHaveBeenCalledTimes(1);
    expect(mockQueuePendingChatWikiQuerySuccess).toHaveBeenCalledTimes(1);
    expect(mockQueuePendingChatWikiQuerySuccess).toHaveBeenCalledWith([], 'chat-test', 'msg-live');
    expect(mockRecordChatWikiQuerySubmitted).not.toHaveBeenCalled();
    expect(mockSendMessage).not.toHaveBeenCalled();
  });
});
