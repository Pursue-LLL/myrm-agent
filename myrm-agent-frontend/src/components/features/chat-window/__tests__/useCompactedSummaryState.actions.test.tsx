import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ArchivedChatMessage, BranchForkResult } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { deferred } from '@/test-utils/deferred';

import { useCompactedSummaryState, type ContextBranchForkDiag } from '../useCompactedSummaryState';
import { archived, branch, kit } from './compactedSummaryKit';
import { setUpSummaryTest } from './compactedSummarySetup';

vi.mock('next/navigation', async () => (await import('./compactedSummaryKit')).navigationMock());
vi.mock('@/services/chat', async () => (await import('./compactedSummaryKit')).chatServiceMock());
vi.mock('@/services/i18nToastService', async () => (await import('./compactedSummaryKit')).toastServiceMock());

setUpSummaryTest();

const chatState = () => useChatStore.getState();
const toastKeys = () => kit.showI18nToast.mock.calls.map(([key]) => key);

describe('useCompactedSummaryState editing the summary', () => {
  it('opens the editor with the current text, and closing it sends nothing', () => {
    const { result } = renderHook(() => useCompactedSummaryState());

    act(() => result.current.handleEdit());
    expect(result.current.isEditing).toBe(true);
    expect(result.current.editValue).toBe('The summary');

    act(() => result.current.handleCancel());
    expect(result.current.isEditing).toBe(false);
    expect(kit.updateCompactionSummary).not.toHaveBeenCalled();
  });

  it('does not open the editor when there is no summary', () => {
    useChatStore.setState({ compactedSummary: null });
    const { result } = renderHook(() => useCompactedSummaryState());

    act(() => result.current.handleEdit());

    expect(result.current.isEditing).toBe(false);
  });

  it('saves the edited text, shows progress meanwhile and closes the editor', async () => {
    const pending = deferred<void>();
    kit.updateCompactionSummary.mockReturnValue(pending.promise);
    const { result } = renderHook(() => useCompactedSummaryState());
    act(() => result.current.handleEdit());
    act(() => result.current.setEditValue('Edited text'));

    let saving!: Promise<void>;
    act(() => {
      saving = result.current.handleSave();
    });
    expect(result.current.isSaving).toBe(true);
    await act(async () => {
      pending.resolve();
      await saving;
    });

    expect(kit.updateCompactionSummary).toHaveBeenCalledExactlyOnceWith('chat-1', 'Edited text');
    expect(chatState().compactedSummary).toBe('Edited text');
    expect(result.current.isEditing).toBe(false);
    expect(result.current.isSaving).toBe(false);
  });

  it('sends nothing without a chat', async () => {
    useChatStore.setState({ chatId: undefined });
    const { result } = renderHook(() => useCompactedSummaryState());
    act(() => result.current.handleEdit());

    await act(async () => result.current.handleSave());

    expect(kit.updateCompactionSummary).not.toHaveBeenCalled();
    expect(result.current.isEditing).toBe(true);
  });

  it('keeps the editor and the text, and tells the user, when the save fails', async () => {
    kit.updateCompactionSummary.mockRejectedValue(new Error('offline'));
    const { result } = renderHook(() => useCompactedSummaryState());
    act(() => result.current.handleEdit());
    act(() => result.current.setEditValue('Edited text'));

    await act(async () => result.current.handleSave());

    expect(result.current.isEditing).toBe(true);
    expect(result.current.editValue).toBe('Edited text');
    expect(result.current.isSaving).toBe(false);
    expect(chatState().compactedSummary).toBe('The summary');
    expect(kit.showI18nToast).toHaveBeenCalledExactlyOnceWith('chat.compactedSummary.summarySaveFailed', undefined, {
      type: 'error',
    });
  });

  it('does not write the text into a chat that was opened while the save was running', async () => {
    const pending = deferred<void>();
    kit.updateCompactionSummary.mockReturnValue(pending.promise);
    const { result } = renderHook(() => useCompactedSummaryState());
    act(() => result.current.handleEdit());
    act(() => result.current.setEditValue('Edited text'));
    let saving!: Promise<void>;
    act(() => {
      saving = result.current.handleSave();
    });

    act(() => useChatStore.setState({ chatId: 'chat-2', compactedSummary: 'Summary of chat 2' }));
    await act(async () => {
      pending.resolve();
      await saving;
    });

    expect(chatState().compactedSummary).toBe('Summary of chat 2');
    expect(result.current.isSaving).toBe(false);
  });
});

describe('useCompactedSummaryState archive', () => {
  it('opens the archive, shows progress while it loads and keeps it for the next opening', async () => {
    const pending = deferred<{ messages: ArchivedChatMessage[] }>();
    kit.getChatArchive.mockReturnValue(pending.promise);
    const { result } = renderHook(() => useCompactedSummaryState());

    let opening!: Promise<void>;
    act(() => {
      opening = result.current.handleViewArchive();
    });
    expect(result.current.isArchiveOpen).toBe(true);
    expect(result.current.isLoadingArchive).toBe(true);
    await act(async () => {
      pending.resolve({ messages: [archived('1'), archived('2')] });
      await opening;
    });
    expect(result.current.archiveMessages.map((item) => item.id)).toEqual(['1', '2']);
    expect(result.current.isLoadingArchive).toBe(false);

    act(() => result.current.setIsArchiveOpen(false));
    await act(async () => result.current.handleViewArchive());

    expect(kit.getChatArchive).toHaveBeenCalledExactlyOnceWith('chat-1');
    expect(result.current.isArchiveOpen).toBe(true);
  });

  it('treats an archive without a message list as empty', async () => {
    kit.getChatArchive.mockResolvedValue({} as { messages: ArchivedChatMessage[] });
    const { result } = renderHook(() => useCompactedSummaryState());

    await act(async () => result.current.handleViewArchive());

    expect(result.current.archiveMessages).toEqual([]);
  });

  it('opens without asking the server when no chat is open', async () => {
    useChatStore.setState({ chatId: undefined });
    const { result } = renderHook(() => useCompactedSummaryState());

    await act(async () => result.current.handleViewArchive());

    expect(result.current.isArchiveOpen).toBe(true);
    expect(kit.getChatArchive).not.toHaveBeenCalled();
  });

  it('tells the user, closes the empty window and asks again next time when the archive cannot be loaded', async () => {
    kit.getChatArchive.mockRejectedValueOnce(new Error('offline'));
    const { result } = renderHook(() => useCompactedSummaryState());

    await act(async () => result.current.handleViewArchive());

    expect(result.current.isArchiveOpen).toBe(false);
    expect(result.current.isLoadingArchive).toBe(false);
    expect(kit.showI18nToast).toHaveBeenCalledExactlyOnceWith('chat.compactedSummary.archiveLoadFailed', undefined, {
      type: 'error',
    });

    kit.getChatArchive.mockResolvedValueOnce({ messages: [archived('1')] });
    await act(async () => result.current.handleViewArchive());

    expect(kit.getChatArchive).toHaveBeenCalledTimes(2);
    expect(result.current.isArchiveOpen).toBe(true);
    expect(result.current.archiveMessages).toHaveLength(1);
  });
});

describe('useCompactedSummaryState opening a snapshot in a new chat', () => {
  const diagPhases = () =>
    (window as Window & { __MYRM_CONTEXT_BRANCH_FORK_DIAG__?: ContextBranchForkDiag }).__MYRM_CONTEXT_BRANCH_FORK_DIAG__
      ?.phase;

  it('forks the snapshot, opens the new chat in a pane and goes there', async () => {
    kit.forkContextBranch.mockResolvedValue({ new_chat_id: 'chat-9' } as BranchForkResult);
    const { result } = renderHook(() => useCompactedSummaryState());

    await act(async () => result.current.handleForkFromBookmark(branch('b1', 'Before refactor')));

    expect(kit.forkContextBranch).toHaveBeenCalledExactlyOnceWith('chat-1', 'b1', 'Before refactor');
    expect(kit.addPane).toHaveBeenCalledExactlyOnceWith('chat-9');
    expect(kit.push).toHaveBeenCalledExactlyOnceWith('/chat-9');
    expect(kit.showI18nToast).toHaveBeenCalledExactlyOnceWith('chat.compactedSummary.bookmarkForkSuccess', undefined, {
      type: 'success',
    });
    expect(diagPhases()).toBe('navigate');
    expect(result.current.forkingBranchId).toBeNull();
  });

  it('reloads the page onto the new chat when the browser is driven by the end-to-end harness', async () => {
    const assign = vi.fn<(url: string) => void>();
    vi.stubGlobal('location', { ...window.location, assign });
    window.__MYRM_E2E_API_BASE__ = 'http://127.0.0.1:1';
    kit.forkContextBranch.mockResolvedValue({ new_chat_id: 'chat-9' } as BranchForkResult);
    const { result } = renderHook(() => useCompactedSummaryState());

    await act(async () => result.current.handleForkFromBookmark(branch('b1')));

    expect(kit.push).toHaveBeenCalledExactlyOnceWith('/chat-9');
    expect(assign).toHaveBeenCalledExactlyOnceWith('/chat-9');
  });

  it('only navigates through the router in an ordinary browser', async () => {
    const assign = vi.fn<(url: string) => void>();
    vi.stubGlobal('location', { ...window.location, assign });
    kit.forkContextBranch.mockResolvedValue({ new_chat_id: 'chat-9' } as BranchForkResult);
    const { result } = renderHook(() => useCompactedSummaryState());

    await act(async () => result.current.handleForkFromBookmark(branch('b1')));

    expect(assign).not.toHaveBeenCalled();
  });

  it('shows which snapshot is opening while the fork runs', async () => {
    const pending = deferred<BranchForkResult>();
    kit.forkContextBranch.mockReturnValue(pending.promise);
    const { result } = renderHook(() => useCompactedSummaryState());

    let forking!: Promise<void>;
    act(() => {
      forking = result.current.handleForkFromBookmark(branch('b1'));
    });
    expect(result.current.forkingBranchId).toBe('b1');
    expect(diagPhases()).toBe('start');
    await act(async () => {
      pending.resolve({ new_chat_id: 'chat-9' } as BranchForkResult);
      await forking;
    });

    expect(result.current.forkingBranchId).toBeNull();
  });

  it('refuses while a reply is streaming, and says why', async () => {
    useChatStore.setState({ loading: true });
    const { result } = renderHook(() => useCompactedSummaryState());

    await act(async () => result.current.handleForkFromBookmark(branch('b1')));

    expect(kit.forkContextBranch).not.toHaveBeenCalled();
    expect(kit.showI18nToast).toHaveBeenCalledExactlyOnceWith('chat.fork.streamingBlocked', undefined, {
      type: 'error',
    });
    expect(diagPhases()).toBe('blocked-loading');
  });

  it('tells the user when the fork fails, and when the answer names no chat', async () => {
    kit.forkContextBranch.mockRejectedValueOnce(new Error('server said no'));
    const { result } = renderHook(() => useCompactedSummaryState());

    await act(async () => result.current.handleForkFromBookmark(branch('b1')));

    expect(toastKeys()).toEqual(['chat.compactedSummary.bookmarkForkFailed']);
    expect(diagPhases()).toBe('api-error');
    expect(
      (window as Window & { __MYRM_CONTEXT_BRANCH_FORK_DIAG__?: ContextBranchForkDiag })
        .__MYRM_CONTEXT_BRANCH_FORK_DIAG__?.error,
    ).toBe('server said no');

    kit.showI18nToast.mockClear();
    kit.forkContextBranch.mockResolvedValueOnce({} as BranchForkResult);
    await act(async () => result.current.handleForkFromBookmark(branch('b1')));

    expect(toastKeys()).toEqual(['chat.compactedSummary.bookmarkForkFailed']);
    expect(kit.push).not.toHaveBeenCalled();
    expect(kit.addPane).not.toHaveBeenCalled();
    expect(result.current.forkingBranchId).toBeNull();
  });

  it('does nothing without a chat or while another snapshot is already opening', async () => {
    const pending = deferred<BranchForkResult>();
    kit.forkContextBranch.mockReturnValue(pending.promise);
    const { result } = renderHook(() => useCompactedSummaryState());
    let forking!: Promise<void>;
    act(() => {
      forking = result.current.handleForkFromBookmark(branch('b1'));
    });

    await act(async () => result.current.handleForkFromBookmark(branch('b2')));
    expect(kit.forkContextBranch).toHaveBeenCalledTimes(1);

    await act(async () => {
      pending.resolve({ new_chat_id: 'chat-9' } as BranchForkResult);
      await forking;
    });
    kit.forkContextBranch.mockClear();
    act(() => useChatStore.setState({ chatId: undefined }));
    await act(async () => result.current.handleForkFromBookmark(branch('b3')));

    expect(kit.forkContextBranch).not.toHaveBeenCalled();
  });
});
