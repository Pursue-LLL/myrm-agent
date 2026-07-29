import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockValidateMessageQuota = vi.hoisted(() => vi.fn(async () => ({ allowed: true })));
const mockRecordChatWikiQueryAttempt = vi.hoisted(() => vi.fn());
const mockRecordChatWikiQuerySubmitted = vi.hoisted(() => vi.fn());
const mockQueuePendingChatWikiQuerySuccess = vi.hoisted(() => vi.fn());
const mockSendMessage = vi.hoisted(() => vi.fn(async () => undefined));
const mockSteerMessage = vi.hoisted(() => vi.fn(async () => true));
const mockEnqueue = vi.hoisted(() => vi.fn());
const mockRecordTurnCapabilitySelectionSubmitted = vi.hoisted(() => vi.fn());
const mockRecordTurnCapabilityOverrideApplied = vi.hoisted(() => vi.fn());
const mockRecordTurnCapabilityOverrideNoop = vi.hoisted(() => vi.fn());
const mockRecordTurnCapabilityQueueEnqueued = vi.hoisted(() => vi.fn());
const mockRecordTurnCapabilitySendCompleted = vi.hoisted(() => vi.fn());
const mockRecordTurnCapabilitySendFailed = vi.hoisted(() => vi.fn());
const mockRecordTurnCapabilityBusyRequeued = vi.hoisted(() => vi.fn());
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

vi.mock('@/services/turnCapabilityMetrics', () => ({
  recordTurnCapabilitySelectionSubmitted: (...args: unknown[]) => mockRecordTurnCapabilitySelectionSubmitted(...args),
  recordTurnCapabilityOverrideApplied: (...args: unknown[]) => mockRecordTurnCapabilityOverrideApplied(...args),
  recordTurnCapabilityOverrideNoop: (...args: unknown[]) => mockRecordTurnCapabilityOverrideNoop(...args),
  recordTurnCapabilityQueueEnqueued: (...args: unknown[]) => mockRecordTurnCapabilityQueueEnqueued(...args),
  recordTurnCapabilitySendCompleted: (...args: unknown[]) => mockRecordTurnCapabilitySendCompleted(...args),
  recordTurnCapabilitySendFailed: (...args: unknown[]) => mockRecordTurnCapabilitySendFailed(...args),
  recordTurnCapabilityBusyRequeued: (...args: unknown[]) => mockRecordTurnCapabilityBusyRequeued(...args),
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
    mockRecordTurnCapabilitySelectionSubmitted.mockClear();
    mockRecordTurnCapabilityOverrideApplied.mockClear();
    mockRecordTurnCapabilityOverrideNoop.mockClear();
    mockRecordTurnCapabilityQueueEnqueued.mockClear();
    mockRecordTurnCapabilitySendCompleted.mockClear();
    mockRecordTurnCapabilitySendFailed.mockClear();
    mockRecordTurnCapabilityBusyRequeued.mockClear();
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
    expect(mockEnqueue).toHaveBeenCalledWith('hello world', [], undefined, null);
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

  it('applies one-turn capability override on handleSubmit', async () => {
    chatStoreRef.state = buildChatState({
      agentConfig: {
        selectedSkillIds: ['skill-a', 'skill-b'],
        selectedMcpNames: ['mcp-a', 'mcp-b'],
        systemPrompt: '',
        useGlobalInstruction: true,
      },
    });
    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    act(() => {
      result.current.setTurnCapabilitySelection({ skillIds: ['skill-b'], mcpNames: null });
    });

    await act(async () => {
      await result.current.handleSubmit();
    });

    expect(mockSendMessage).toHaveBeenCalledWith(
      'hello world',
      undefined,
      undefined,
      undefined,
      undefined,
      expect.objectContaining({
        selectedSkillIds: ['skill-b'],
        selectedMcpNames: ['mcp-a', 'mcp-b'],
      }),
      true,
    );
    expect(mockRecordTurnCapabilitySelectionSubmitted).toHaveBeenCalledTimes(1);
  });

  it('consumes one-turn capability selection on direct queue submit', async () => {
    chatStoreRef.state = buildChatState({
      agentConfig: {
        selectedSkillIds: ['skill-a', 'skill-b'],
        selectedMcpNames: ['mcp-a', 'mcp-b'],
        systemPrompt: '',
        useGlobalInstruction: true,
      },
    });
    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    act(() => {
      result.current.setTurnCapabilitySelection({ skillIds: ['skill-b'], mcpNames: ['mcp-a'] });
    });

    await act(async () => {
      await result.current.handleQueueSubmit();
    });

    expect(mockEnqueue).toHaveBeenCalledWith(
      'hello world',
      [],
      undefined,
      { skillIds: ['skill-b'], mcpNames: ['mcp-a'] },
    );
    expect(mockRecordTurnCapabilitySelectionSubmitted).toHaveBeenCalledTimes(1);
    expect(mockRecordTurnCapabilityQueueEnqueued).toHaveBeenCalledTimes(1);
  });

  it('records busy requeue without applied metric on direct busy fallback', async () => {
    const busyError = new Error('busy');
    busyError.name = 'AgentBusyError';
    mockSendMessage.mockRejectedValueOnce(busyError);
    chatStoreRef.state = buildChatState({
      agentConfig: {
        selectedSkillIds: ['skill-a', 'skill-b'],
        selectedMcpNames: ['mcp-a', 'mcp-b'],
        systemPrompt: '',
        useGlobalInstruction: true,
      },
    });

    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    act(() => {
      result.current.setTurnCapabilitySelection({ skillIds: ['skill-b'], mcpNames: ['mcp-a'] });
    });

    await act(async () => {
      await result.current.handleSubmit();
      await Promise.resolve();
    });

    expect(mockRecordTurnCapabilitySelectionSubmitted).toHaveBeenCalledTimes(1);
    expect(mockRecordTurnCapabilityBusyRequeued).toHaveBeenCalledTimes(1);
    expect(mockRecordTurnCapabilityQueueEnqueued).toHaveBeenCalledTimes(1);
    expect(mockRecordTurnCapabilityOverrideApplied).toHaveBeenCalledTimes(0);
  });

  it('maps direct send failure to enum reason', async () => {
    const networkError = new Error('network timeout');
    networkError.name = 'TypeError';
    mockSendMessage.mockRejectedValueOnce(networkError);
    chatStoreRef.state = buildChatState({
      agentConfig: {
        selectedSkillIds: ['skill-a', 'skill-b'],
        selectedMcpNames: ['mcp-a', 'mcp-b'],
        systemPrompt: '',
        useGlobalInstruction: true,
      },
    });

    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    act(() => {
      result.current.setTurnCapabilitySelection({ skillIds: ['skill-b'], mcpNames: ['mcp-a'] });
    });

    await act(async () => {
      await result.current.handleSubmit();
      await Promise.resolve();
    });

    expect(mockRecordTurnCapabilitySendFailed).toHaveBeenCalledTimes(1);
    expect(mockRecordTurnCapabilitySendFailed).toHaveBeenCalledWith('direct', 'network_error', 'chat:chat-test');
  });

  it('maps fatal 5xx failure to server_error enum reason', async () => {
    const { FatalNetworkError } = await import('@/lib/utils/networkResilience');
    mockSendMessage.mockRejectedValueOnce(new FatalNetworkError('upstream 500', { status: 500 }));
    chatStoreRef.state = buildChatState({
      agentConfig: {
        selectedSkillIds: ['skill-a', 'skill-b'],
        selectedMcpNames: ['mcp-a', 'mcp-b'],
        systemPrompt: '',
        useGlobalInstruction: true,
      },
    });

    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    act(() => {
      result.current.setTurnCapabilitySelection({ skillIds: ['skill-b'], mcpNames: ['mcp-a'] });
    });

    await act(async () => {
      await result.current.handleSubmit();
      await Promise.resolve();
    });

    expect(mockRecordTurnCapabilitySendFailed).toHaveBeenCalledTimes(1);
    expect(mockRecordTurnCapabilitySendFailed).toHaveBeenCalledWith('direct', 'server_error', 'chat:chat-test');
  });
});
