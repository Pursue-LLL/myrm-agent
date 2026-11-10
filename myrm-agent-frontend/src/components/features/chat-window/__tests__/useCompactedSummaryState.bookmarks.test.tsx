import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ContextBranchRecord } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { deferred } from '@/test-utils/deferred';

import {
  bookmarkDisplayLabel,
  reportContextBranchForkDiag,
  useCompactedSummaryState,
  type ContextBranchForkDiag,
} from '../useCompactedSummaryState';
import { branch, kit } from './compactedSummaryKit';
import { setUpSummaryTest } from './compactedSummarySetup';

vi.mock('next/navigation', async () => (await import('./compactedSummaryKit')).navigationMock());
vi.mock('@/services/chat', async () => (await import('./compactedSummaryKit')).chatServiceMock());
vi.mock('@/services/i18nToastService', async () => (await import('./compactedSummaryKit')).toastServiceMock());

setUpSummaryTest();

const chatState = () => useChatStore.getState();

function switchToChat(chatId: string): void {
  act(() => useChatStore.setState({ chatId }));
}

describe('bookmarkDisplayLabel', () => {
  it('uses the trimmed label when there is one', () => {
    expect(bookmarkDisplayLabel(branch('a', '  Before refactor  '))).toBe('Before refactor');
  });

  it('falls back to the file name of the snapshot, whichever separator the path uses', () => {
    expect(bookmarkDisplayLabel(branch('a', '   ', '/data/snapshots/state.json'))).toBe('state.json');
    expect(bookmarkDisplayLabel(branch('a', '', 'C:\\data\\snapshots\\win.json'))).toBe('win.json');
  });

  it('falls back to the whole path when it ends in a separator', () => {
    expect(bookmarkDisplayLabel(branch('a', '', '/data/snapshots/'))).toBe('/data/snapshots/');
  });
});

describe('reportContextBranchForkDiag', () => {
  it('leaves the latest fork step on window for diagnostics', () => {
    const diag: ContextBranchForkDiag = { phase: 'start', at: 1, chatId: 'chat-1', branchId: 'b1' };

    reportContextBranchForkDiag(diag);

    expect(
      (window as Window & { __MYRM_CONTEXT_BRANCH_FORK_DIAG__?: ContextBranchForkDiag })
        .__MYRM_CONTEXT_BRANCH_FORK_DIAG__,
    ).toBe(diag);
  });
});

describe('useCompactedSummaryState bookmarks', () => {
  it('lists the five most recent snapshots, newest first', () => {
    useChatStore.setState({ contextBranches: ['1', '2', '3', '4', '5', '6', '7'].map((id) => branch(id)) });

    const { result } = renderHook(() => useCompactedSummaryState());

    expect(result.current.bookmarks.map((item) => item.branch_id)).toEqual(['7', '6', '5', '4', '3']);
  });

  describe('loading', () => {
    it('clears the list and the error when no chat is open', async () => {
      useChatStore.setState({
        chatId: undefined,
        contextBranches: [branch('a')],
        contextBranchesLoadError: 'load_failed',
      });
      const { result } = renderHook(() => useCompactedSummaryState());

      let returned: ContextBranchRecord[] = [branch('x')];
      await act(async () => {
        returned = await result.current.loadBookmarks();
      });

      expect(returned).toEqual([]);
      expect(chatState().contextBranches).toEqual([]);
      expect(chatState().contextBranchesLoadError).toBeNull();
      expect(kit.listContextBranches).not.toHaveBeenCalled();
    });

    it("stores the chat's snapshots, clears an earlier error and shows progress while it waits", async () => {
      useChatStore.setState({ contextBranchesLoadError: 'load_failed' });
      const pending = deferred<ContextBranchRecord[]>();
      kit.listContextBranches.mockReturnValue(pending.promise);
      const { result } = renderHook(() => useCompactedSummaryState());

      let loading!: Promise<ContextBranchRecord[]>;
      act(() => {
        loading = result.current.loadBookmarks();
      });
      expect(result.current.bookmarksLoading).toBe(true);

      let returned: ContextBranchRecord[] = [];
      await act(async () => {
        pending.resolve(['1', '2', '3', '4', '5', '6'].map((id) => branch(id)));
        returned = await loading;
      });

      expect(kit.listContextBranches).toHaveBeenCalledExactlyOnceWith('chat-1');
      expect(returned.map((item) => item.branch_id)).toEqual(['6', '5', '4', '3', '2']);
      expect(chatState().contextBranches).toHaveLength(6);
      expect(chatState().contextBranchesLoadError).toBeNull();
      expect(result.current.bookmarksLoading).toBe(false);
    });

    it('records a failure for the retry control and returns nothing', async () => {
      kit.listContextBranches.mockRejectedValue(new Error('offline'));
      const { result } = renderHook(() => useCompactedSummaryState());

      let returned: ContextBranchRecord[] = [branch('x')];
      await act(async () => {
        returned = await result.current.loadBookmarks();
      });

      expect(returned).toEqual([]);
      expect(chatState().contextBranchesLoadError).toBe('load_failed');
      expect(result.current.bookmarksLoading).toBe(false);
    });

    it('drops the answer when another chat was opened meanwhile', async () => {
      const pending = deferred<ContextBranchRecord[]>();
      kit.listContextBranches.mockReturnValue(pending.promise);
      const { result } = renderHook(() => useCompactedSummaryState());
      let loading!: Promise<ContextBranchRecord[]>;
      act(() => {
        loading = result.current.loadBookmarks();
      });

      switchToChat('chat-2');
      let returned: ContextBranchRecord[] = [branch('x')];
      await act(async () => {
        pending.resolve([branch('old')]);
        returned = await loading;
      });

      expect(returned).toEqual([]);
      expect(chatState().contextBranches).toEqual([]);
    });

    it("stops showing progress once the old chat's answer has been dropped", async () => {
      const pending = deferred<ContextBranchRecord[]>();
      kit.listContextBranches.mockReturnValue(pending.promise);
      const { result } = renderHook(() => useCompactedSummaryState());
      let loading!: Promise<ContextBranchRecord[]>;
      act(() => {
        loading = result.current.loadBookmarks();
      });

      switchToChat('chat-2');
      await act(async () => {
        pending.resolve([branch('old')]);
        await loading;
      });

      expect(result.current.bookmarksLoading).toBe(false);
    });

    it('does not blame the new chat for a failure of the old one', async () => {
      const pending = deferred<ContextBranchRecord[]>();
      kit.listContextBranches.mockReturnValue(pending.promise);
      const { result } = renderHook(() => useCompactedSummaryState());
      let loading!: Promise<ContextBranchRecord[]>;
      act(() => {
        loading = result.current.loadBookmarks();
      });

      switchToChat('chat-2');
      await act(async () => {
        pending.reject(new Error('timed out'));
        await loading;
      });

      expect(chatState().contextBranchesLoadError).toBeNull();
    });
  });

  describe('saving the latest snapshot', () => {
    it('saves it, reloads the list and says so', async () => {
      kit.createContextBranch.mockResolvedValue(branch('new'));
      kit.listContextBranches.mockResolvedValue([branch('new')]);
      const { result } = renderHook(() => useCompactedSummaryState());

      await act(async () => result.current.handleSaveBookmark());

      expect(kit.createContextBranch).toHaveBeenCalledExactlyOnceWith('chat-1', {
        snapshot_path: '/snapshots/latest.json',
      });
      expect(chatState().contextBranches.map((item) => item.branch_id)).toEqual(['new']);
      expect(kit.showI18nToast).toHaveBeenCalledExactlyOnceWith('chat.compactedSummary.bookmarkSaved', undefined, {
        type: 'success',
      });
      expect(result.current.isSavingBookmark).toBe(false);
    });

    it('tells the user when it could not be saved', async () => {
      kit.createContextBranch.mockRejectedValue(new Error('disk full'));
      const { result } = renderHook(() => useCompactedSummaryState());

      await act(async () => result.current.handleSaveBookmark());

      expect(kit.listContextBranches).not.toHaveBeenCalled();
      expect(kit.showI18nToast).toHaveBeenCalledExactlyOnceWith('chat.compactedSummary.bookmarkSaveFailed', undefined, {
        type: 'error',
      });
      expect(result.current.isSavingBookmark).toBe(false);
    });

    it('does nothing without a chat or a snapshot, or while a save is running', async () => {
      const pending = deferred<ContextBranchRecord>();
      kit.createContextBranch.mockReturnValue(pending.promise);
      kit.listContextBranches.mockResolvedValue([]);
      const { result } = renderHook(() => useCompactedSummaryState());

      let first!: Promise<void>;
      act(() => {
        first = result.current.handleSaveBookmark();
      });
      await act(async () => result.current.handleSaveBookmark());
      expect(kit.createContextBranch).toHaveBeenCalledTimes(1);
      await act(async () => {
        pending.resolve(branch('new'));
        await first;
      });

      kit.createContextBranch.mockClear();
      act(() => useChatStore.setState({ lastCompactionMeta: { tokensSaved: 5 } }));
      await act(async () => result.current.handleSaveBookmark());
      act(() =>
        useChatStore.setState({ lastCompactionMeta: { tokensSaved: 5, snapshotPath: '/s.json' }, chatId: undefined }),
      );
      await act(async () => result.current.handleSaveBookmark());

      expect(kit.createContextBranch).not.toHaveBeenCalled();
    });
  });
});
