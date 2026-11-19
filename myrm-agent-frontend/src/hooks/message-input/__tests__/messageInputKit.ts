/**
 * [INPUT]
 * - vitest::vi (POS: 模块替身登记)
 *
 * [OUTPUT]
 * - mock* / chatStoreRef: 提交、排队、草稿、输入历史、埋点、toast 等边界的替身句柄，以及聊天 store 的可变状态
 * - buildChatState: 构造一份聊天 store 状态（可覆盖字段），测试用例赋给 chatStoreRef.state
 * - resetMessageInputMocks: 清空替身调用记录，并把 store 状态恢复为默认
 *
 * [POS]
 * useMessageInput 行为测试的共享底座。必须先于被测 Hook 导入：vi.mock 在本模块求值时登记，
 * 各用例在测试体内再动态导入 useMessageInput。
 */
import { vi } from 'vitest';

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

export {
  chatStoreRef,
  mockAddInputHistory,
  mockEnqueue,
  mockQueuePendingChatWikiQuerySuccess,
  mockRecordChatWikiQueryAttempt,
  mockRecordChatWikiQuerySubmitted,
  mockRecordTurnCapabilityBusyRequeued,
  mockRecordTurnCapabilityOverrideApplied,
  mockRecordTurnCapabilityOverrideNoop,
  mockRecordTurnCapabilityQueueEnqueued,
  mockRecordTurnCapabilitySelectionSubmitted,
  mockRecordTurnCapabilitySendFailed,
  mockRedirectMessage,
  mockSendMessage,
  mockSetFiles,
  mockSetInputMessage,
  mockSetPendingArchiveRestoreActions,
  mockSteerMessage,
  mockToastInfo,
  mockUseDraftPersistence,
  mockValidateMessageQuota,
};

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

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    info: (...args: unknown[]) => mockToastInfo(...args),
    error: vi.fn(),
    warning: vi.fn(),
    loading: vi.fn(),
    success: vi.fn(),
  },
}));

export function buildChatState(overrides: Partial<Record<string, unknown>> = {}): Record<string, unknown> {
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
    loading: false,
    messages: [],
    agentConfig: null,
    incognitoMode: false,
    ...overrides,
  };
}

/** Clears every stand-in's calls and puts the chat store back to its default state. */
export function resetMessageInputMocks(): void {
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
}
