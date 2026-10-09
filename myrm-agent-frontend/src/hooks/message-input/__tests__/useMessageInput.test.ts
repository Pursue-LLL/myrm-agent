import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockValidateMessageQuota = vi.hoisted(() =>
  vi.fn<(...args: unknown[]) => Promise<{ allowed: boolean }>>(async () => ({ allowed: true })),
);
const mockRecordChatWikiQueryAttempt = vi.hoisted(() => vi.fn());
const mockRecordChatWikiQuerySubmitted = vi.hoisted(() => vi.fn());
const mockQueuePendingChatWikiQuerySuccess = vi.hoisted(() => vi.fn());
const mockSendMessage = vi.hoisted(() => vi.fn<(...args: unknown[]) => Promise<boolean>>(async () => true));
const mockSteerMessage = vi.hoisted(() => vi.fn<(...args: unknown[]) => Promise<boolean>>(async () => true));
const mockRedirectMessage = vi.hoisted(() => vi.fn<(...args: unknown[]) => Promise<boolean>>(async () => true));
const mockEnqueue = vi.hoisted(() => vi.fn<(...args: unknown[]) => number>(() => 1));
const mockSetFiles = vi.hoisted(() => vi.fn());
const mockAddInputHistory = vi.hoisted(() => vi.fn());
const mockUseDraftPersistence = vi.hoisted(() => vi.fn());
const mockToastInfo = vi.hoisted(() => vi.fn());
const mockRecordTurnCapabilitySelectionSubmitted = vi.hoisted(() => vi.fn());
const mockRecordTurnCapabilityOverrideApplied = vi.hoisted(() => vi.fn());
const mockRecordTurnCapabilityOverrideNoop = vi.hoisted(() => vi.fn());
const mockRecordTurnCapabilityQueueEnqueued = vi.hoisted(() => vi.fn());
const mockRecordTurnCapabilitySendFailed = vi.hoisted(() => vi.fn());
const mockRecordTurnCapabilityBusyRequeued = vi.hoisted(() => vi.fn());
const mockSetInputMessage = vi.hoisted(() => vi.fn());
const mockSetPendingArchiveRestoreActions = vi.hoisted(() => vi.fn());
const mockClearDraft = vi.hoisted(() => vi.fn());
const chatStoreRef = vi.hoisted(() => ({ state: {} as Record<string, unknown> }));

// Renders ICU values into the key so assertions can see what the user would be told.
const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key}:${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/billing/useQuotaGuard', () => ({
  useQuotaGuard: () => ({
    validateMessageQuota: (...args: unknown[]) => mockValidateMessageQuota(...args),
  }),
}));

vi.mock('@/hooks/shared/useDraftPersistence', () => ({
  useDraftPersistence: (...args: unknown[]) => {
    mockUseDraftPersistence(...args);
    return {
      initialDraft: '',
      clearDraft: (...clearArgs: unknown[]) => mockClearDraft(...clearArgs),
    };
  },
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
    pausedReason: null,
    editingId: null,
    enqueue: (...args: unknown[]) => mockEnqueue(...args),
    editMessage: vi.fn(),
    removeMessage: vi.fn(),
    clearQueue: vi.fn(),
    reorder: vi.fn(),
    setEditingId: vi.fn(),
    resume: vi.fn(),
  }),
}));

vi.mock('@/hooks/message-input/useQueueDrain', () => ({
  useQueueDrain: vi.fn(),
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
  addInputHistory: (...args: unknown[]) => mockAddInputHistory(...args),
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
  recordTurnCapabilitySendFailed: (...args: unknown[]) => mockRecordTurnCapabilitySendFailed(...args),
  recordTurnCapabilityBusyRequeued: (...args: unknown[]) => mockRecordTurnCapabilityBusyRequeued(...args),
}));

vi.mock('@/services/chat', () => ({
  compactChat: vi.fn(),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    info: (...args: unknown[]) => mockToastInfo(...args),
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
    redirectMessage: (...args: unknown[]) => mockRedirectMessage(...args),
    actionMode: 'agent',
    setActionMode: vi.fn(),
    files: [],
    setFiles: (...args: unknown[]) => mockSetFiles(...args),
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
    incognitoMode: false,
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
    mockRedirectMessage.mockClear();
    mockEnqueue.mockClear();
    mockEnqueue.mockReturnValue(1);
    mockSetFiles.mockClear();
    mockAddInputHistory.mockClear();
    mockUseDraftPersistence.mockClear();
    mockToastInfo.mockClear();
    mockSetInputMessage.mockClear();
    mockSetPendingArchiveRestoreActions.mockClear();
    mockClearDraft.mockClear();
    mockQueuePendingChatWikiQuerySuccess.mockClear();
    mockRecordTurnCapabilitySelectionSubmitted.mockClear();
    mockRecordTurnCapabilityOverrideApplied.mockClear();
    mockRecordTurnCapabilityOverrideNoop.mockClear();
    mockRecordTurnCapabilityQueueEnqueued.mockClear();
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
      undefined,
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

  describe('an instruction the running turn cannot take', () => {
    it('queues a refused steer and tells the user it is sent after the current task', async () => {
      chatStoreRef.state = buildChatState({ loading: true });
      mockSteerMessage.mockResolvedValueOnce(false);
      mockEnqueue.mockReturnValue(2);
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      await act(async () => {
        await result.current.handleSteerSubmit();
      });

      expect(mockRecordChatWikiQueryAttempt).toHaveBeenCalledTimes(1);
      expect(mockEnqueue).toHaveBeenCalledWith('hello world', [], undefined, null);
      expect(mockToastInfo).toHaveBeenCalledWith('queue.added_with_position:{"position":2}');
      expect(mockSendMessage).not.toHaveBeenCalled();
      expect(mockSetInputMessage).toHaveBeenCalledWith('');
    });

    it('queues a refused steer without a notice when the agent has gone idle', async () => {
      mockSteerMessage.mockResolvedValueOnce(false);
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      await act(async () => {
        await result.current.handleSteerSubmit();
      });

      expect(mockEnqueue).toHaveBeenCalledWith('hello world', [], undefined, null);
      expect(mockToastInfo).not.toHaveBeenCalled();
      expect(mockSendMessage).not.toHaveBeenCalled();
    });

    it('hands a failed redirect to steer as the same composed message and queues it, validating and recording once', async () => {
      const pendingSkill = { skillNames: ['pdf'] };
      chatStoreRef.state = buildChatState({
        loading: true,
        pendingExplicitSkillActivation: pendingSkill,
        setPendingExplicitSkillActivation: (value: unknown) => {
          chatStoreRef.state.pendingExplicitSkillActivation = value;
        },
      });
      mockRedirectMessage.mockResolvedValueOnce(false);
      mockSteerMessage.mockResolvedValueOnce(false);
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      await act(async () => {
        await result.current.handleRedirectSubmit();
      });

      expect(mockRedirectMessage).toHaveBeenCalledWith('[use pdf] hello world');
      expect(mockSteerMessage).toHaveBeenCalledWith('[use pdf] hello world');
      expect(mockEnqueue).toHaveBeenCalledWith('[use pdf] hello world', [], undefined, null);
      expect(mockSendMessage).not.toHaveBeenCalled();
      expect(mockValidateMessageQuota).toHaveBeenCalledTimes(1);
      expect(mockRecordChatWikiQueryAttempt).toHaveBeenCalledTimes(1);
    });

    it('does not queue a redirect the running turn accepted', async () => {
      chatStoreRef.state = buildChatState({ loading: true });
      mockRedirectMessage.mockResolvedValueOnce(true);
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      await act(async () => {
        await result.current.handleRedirectSubmit();
      });

      expect(mockQueuePendingChatWikiQuerySuccess).toHaveBeenCalledTimes(1);
      expect(mockSteerMessage).not.toHaveBeenCalled();
      expect(mockEnqueue).not.toHaveBeenCalled();
      expect(mockSendMessage).not.toHaveBeenCalled();
    });
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
      {
        source: 'direct',
        effectiveSkillCount: 1,
        effectiveMcpCount: 2,
      },
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

    expect(mockEnqueue).toHaveBeenCalledWith('hello world', [], undefined, {
      skillIds: ['skill-b'],
      mcpNames: ['mcp-a'],
    });
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

  it('does not emit client failure metric for fatal 5xx failures', async () => {
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

    expect(mockRecordTurnCapabilitySendFailed).not.toHaveBeenCalled();
  });

  it('routes handleSubmit to redirectMessage when loading=true and busyInputMode is redirect (default)', async () => {
    chatStoreRef.state = buildChatState({
      loading: true,
      inputMessage: 'redirect instruction',
    });

    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    await act(async () => {
      await result.current.handleSubmit();
    });

    expect(mockRedirectMessage).toHaveBeenCalledWith('redirect instruction');
    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it('routes handleSubmit to enqueue when loading=true and busyInputMode is queue', async () => {
    chatStoreRef.state = buildChatState({
      loading: true,
      inputMessage: 'follow-up task',
      agentConfig: {
        busyInputMode: 'queue',
      },
    });

    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());

    await act(async () => {
      await result.current.handleSubmit();
    });

    expect(mockEnqueue).toHaveBeenCalledWith('follow-up task', [], undefined, null);
    expect(mockRedirectMessage).not.toHaveBeenCalled();
    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  describe('queue attachments', () => {
    const attachment = { id: 'file-1', name: 'notes.zip', status: 'done' };

    it('moves the staged attachments into the queued message and empties the composer', async () => {
      chatStoreRef.state = buildChatState({ files: [attachment] });
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      await act(async () => {
        await result.current.handleQueueSubmit();
      });

      expect(mockEnqueue).toHaveBeenCalledWith('hello world', [attachment], undefined, null);
      expect(mockSetFiles).toHaveBeenCalledWith([]);
    });

    it('queues a busy submit that carries attachments instead of redirecting it as text only', async () => {
      chatStoreRef.state = buildChatState({ loading: true, inputMessage: 'see attached', files: [attachment] });
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      await act(async () => {
        await result.current.handleSubmit();
      });

      expect(mockEnqueue).toHaveBeenCalledWith('see attached', [attachment], undefined, null);
      expect(mockRedirectMessage).not.toHaveBeenCalled();
      expect(mockSteerMessage).not.toHaveBeenCalled();
    });

    it('requeues a busy-refused message with the attachments it was sent with and reports its real position', async () => {
      const busyError = new Error('busy');
      busyError.name = 'AgentBusyError';
      chatStoreRef.state = buildChatState({ files: [attachment] });
      mockSendMessage.mockImplementationOnce(async () => {
        // By the time the refusal reaches the hook the store has already emptied the composer attachments.
        chatStoreRef.state.files = [];
        throw busyError;
      });
      mockEnqueue.mockReturnValue(3);
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      await act(async () => {
        await result.current.handleSubmit();
        await Promise.resolve();
      });

      expect(mockEnqueue).toHaveBeenCalledWith('hello world', [attachment], undefined, null);
      expect(mockToastInfo).toHaveBeenCalledWith('queue.added_with_position:{"position":3}');
    });

    it('restores the sent attachments when the archive restore action is rejected', async () => {
      const { FatalNetworkError, ARCHIVE_RESTORE_ACTION_INVALID } = await import('@/lib/utils/networkResilience');
      chatStoreRef.state = buildChatState({ files: [attachment] });
      mockSendMessage.mockImplementationOnce(async () => {
        chatStoreRef.state.files = [];
        throw new FatalNetworkError('invalid restore action', {
          status: 400,
          errorCode: ARCHIVE_RESTORE_ACTION_INVALID,
        });
      });
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      await act(async () => {
        await result.current.handleSubmit();
        await Promise.resolve();
      });

      expect(mockSetFiles).toHaveBeenCalledWith([attachment]);
      expect(mockSetInputMessage).toHaveBeenLastCalledWith('hello world');
    });
  });

  it('does not count a locally refused request as a settled capability override', async () => {
    mockSendMessage.mockResolvedValueOnce(false);
    chatStoreRef.state = buildChatState({
      agentConfig: {
        selectedSkillIds: ['skill-a', 'skill-b'],
        selectedMcpNames: ['mcp-a'],
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
      await Promise.resolve();
    });

    expect(mockRecordTurnCapabilityOverrideApplied).not.toHaveBeenCalled();
    expect(mockRecordTurnCapabilityOverrideNoop).not.toHaveBeenCalled();
  });

  describe('incognito sessions', () => {
    it('keeps drafts and input history off disk', async () => {
      chatStoreRef.state = buildChatState({ incognitoMode: true });
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      await act(async () => {
        await result.current.handleSubmit();
      });

      expect(mockUseDraftPersistence).toHaveBeenCalledWith(null, expect.any(String));
      expect(mockAddInputHistory).not.toHaveBeenCalled();
      expect(mockSendMessage).toHaveBeenCalledTimes(1);
    });

    it('persists drafts and input history in regular sessions', async () => {
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      await act(async () => {
        await result.current.handleSubmit();
      });

      expect(mockUseDraftPersistence).toHaveBeenCalledWith('chat-test', expect.any(String));
      expect(mockAddInputHistory).toHaveBeenCalledTimes(1);
    });
  });
});
