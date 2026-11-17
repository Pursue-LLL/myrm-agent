import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const chatStoreRef = vi.hoisted(() => ({ state: {} as Record<string, unknown> }));
const mockCompactChat = vi.hoisted(() => vi.fn());
const mockToastSuccess = vi.hoisted(() => vi.fn());

vi.mock('@/services/chat', () => ({ compactChat: mockCompactChat }));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    loading: () => 'toast-1',
    success: mockToastSuccess,
    info: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('@/hooks/billing/useQuotaGuard', () => ({
  useQuotaGuard: () => ({ validateMessageQuota: vi.fn(async () => ({ allowed: true })) }),
}));

vi.mock('@/hooks/shared/useDraftPersistence', () => ({
  useDraftPersistence: () => ({ initialDraft: '', clearDraft: vi.fn() }),
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
    enqueue: vi.fn(() => 1),
    editMessage: vi.fn(),
    removeMessage: vi.fn(),
    clearQueue: vi.fn(),
    reorder: vi.fn(),
    setEditingId: vi.fn(),
    resume: vi.fn(),
  }),
}));

vi.mock('@/hooks/message-input/useQueueDrain', () => ({ useQueueDrain: vi.fn() }));

vi.mock('@/hooks/message-input/useInputFileUpload', () => ({
  useInputFileUpload: () => ({ isUploadingPaste: false, handlePaste: vi.fn(), handleDroppedFiles: vi.fn() }),
}));

describe('useMessageInput /compact', () => {
  beforeEach(() => {
    localStorage.clear();
    // With the warning switched off, `/compact <topic>` compacts straight away.
    localStorage.setItem('dontRemindCompact', 'true');
    mockCompactChat.mockReset();
    mockToastSuccess.mockReset();
    chatStoreRef.state = {
      chatId: 'chat-test',
      sendMessage: vi.fn(),
      steerMessage: vi.fn(),
      redirectMessage: vi.fn(),
      actionMode: 'agent',
      setActionMode: vi.fn(),
      files: [],
      setFiles: vi.fn(),
      hideAttachList: false,
      setHideAttachList: vi.fn(),
      stopMessage: vi.fn(),
      clearCurrentSessionMessageId: vi.fn(),
      inputMessage: '',
      setInputMessage: vi.fn(),
      pendingArchiveRestoreActions: [],
      setPendingArchiveRestoreActions: vi.fn(),
      loadMessages: vi.fn(),
      loading: false,
      messages: [],
      agentConfig: null,
      incognitoMode: false,
    };
  });

  async function submit(text: string): Promise<void> {
    chatStoreRef.state.inputMessage = text;
    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    const { result } = renderHook(() => useMessageInput());
    await act(async () => {
      await result.current.handleSubmit();
    });
  }

  it('names the topic the server kept in the success toast, not the whole text that was typed', async () => {
    const typed = 'billing '.repeat(60).trim();
    const kept = typed.slice(0, 200).trim();
    mockCompactChat.mockResolvedValue({
      compacted: true,
      message_count: 12,
      tokens_saved: 3400,
      reason: null,
      focus_topic: kept,
    });

    await submit(`/compact ${typed}`);

    expect(mockCompactChat).toHaveBeenCalledWith('chat-test', typed);
    expect(mockToastSuccess).toHaveBeenCalledWith(`compact.success (${kept})`, { id: 'toast-1' });
  });

  it('shows no topic when none was given', async () => {
    mockCompactChat.mockResolvedValue({
      compacted: true,
      message_count: 12,
      tokens_saved: 3400,
      reason: null,
      focus_topic: '',
    });

    await submit('/compact');

    expect(mockCompactChat).toHaveBeenCalledWith('chat-test', undefined);
    expect(mockToastSuccess).toHaveBeenCalledWith('compact.success', { id: 'toast-1' });
  });
});
