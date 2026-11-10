import { act, renderHook } from '@testing-library/react';
import type { ChangeEvent } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const chatStoreRef = vi.hoisted(() => ({ state: {} as Record<string, unknown> }));

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

function typed(value: string): ChangeEvent<HTMLTextAreaElement> {
  return { target: { value } } as ChangeEvent<HTMLTextAreaElement>;
}

describe('useMessageInput link prompt', () => {
  const setInputMessage = vi.fn();
  const clearCurrentSessionMessageId = vi.fn();

  beforeEach(() => {
    localStorage.clear();
    setInputMessage.mockReset();
    clearCurrentSessionMessageId.mockReset();
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
      clearCurrentSessionMessageId,
      inputMessage: '',
      setInputMessage,
      pendingArchiveRestoreActions: [],
      setPendingArchiveRestoreActions: vi.fn(),
      loadMessages: vi.fn(),
      loading: false,
      messages: [],
      agentConfig: null,
      incognitoMode: false,
    };
  });

  async function renderInput() {
    const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
    return renderHook(() => useMessageInput());
  }

  it('stores whatever is typed and asks about a link without an @, once per message', async () => {
    const { result } = await renderInput();

    act(() => result.current.handleInputChange(typed('see https://example.com')));
    expect(setInputMessage).toHaveBeenLastCalledWith('see https://example.com');
    expect(result.current.showLinkDialog).toBe(true);

    act(() => result.current.handleSkipAtSymbol());
    expect(setInputMessage).toHaveBeenCalledTimes(1);
    act(() => result.current.handleInputChange(typed('see https://example.com now')));

    expect(setInputMessage).toHaveBeenLastCalledWith('see https://example.com now');
    expect(result.current.showLinkDialog).toBe(false);
  });

  it('adds the @ to the text that is in the box when the user says yes', async () => {
    chatStoreRef.state.inputMessage = 'read https://example.com';
    const { result } = await renderInput();
    act(() => result.current.handleInputChange(typed('read https://example.com')));

    act(() => result.current.handleAddAtSymbol());

    expect(setInputMessage).toHaveBeenLastCalledWith('read @https://example.com');
    expect(result.current.showLinkDialog).toBe(false);
  });

  it('does not ask about text without a link, and clears the message id when the box is emptied', async () => {
    const { result } = await renderInput();

    act(() => result.current.handleInputChange(typed('just words')));
    expect(result.current.showLinkDialog).toBe(false);
    expect(clearCurrentSessionMessageId).not.toHaveBeenCalled();

    act(() => result.current.handleInputChange(typed('   ')));
    expect(clearCurrentSessionMessageId).toHaveBeenCalledTimes(1);
  });

  it('keeps the message id while files are still attached to an emptied box', async () => {
    chatStoreRef.state.files = [{ name: 'notes.txt' }];
    const { result } = await renderInput();

    act(() => result.current.handleInputChange(typed('')));

    expect(clearCurrentSessionMessageId).not.toHaveBeenCalled();
  });

  it('shares the "do not remind me" state with the dialog', async () => {
    const { result } = await renderInput();
    act(() => result.current.setDontRemindAgain(true));
    expect(result.current.dontRemindAgain).toBe(true);

    act(() => result.current.handleInputChange(typed('see https://example.com')));

    expect(result.current.showLinkDialog).toBe(false);
  });
});
