'use client';

/**
 * [INPUT]
 * - useChatStore from '@/store/useChatStore'
 * - useWorkspaceStore from '@/store/useWorkspaceStore'
 * - services/chat from '@/services/chat'
 *
 * [OUTPUT]
 * - useCompactedSummaryState: Custom hook for managing compaction summary view state and actions
 *
 * [POS]
 * Extracted state manager for CompactedSummaryView (Item 27 refactor).
 * Decouples bookmarks loading, editing, saving, and branch forking logic.
 * Strictly typed, zero `any`, file length < 250 lines.
 */

import { useState, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import useChatStore from '@/store/useChatStore';
import useWorkspaceStore from '@/store/useWorkspaceStore';
import { useShallow } from 'zustand/react/shallow';
import {
  createContextBranch,
  forkContextBranch,
  getChatArchive,
  listContextBranches,
  updateCompactionSummary,
  type ContextBranchRecord,
} from '@/services/chat';
import type { Message } from '@/store/chat/types';
import { showI18nToast } from '@/services/i18nToastService';
import { resolveE2eApiBase } from '@/lib/deploy-mode';

const MAX_BOOKMARKS_DISPLAY = 5;

export type ContextBranchForkDiag = {
  phase: string;
  at: number;
  chatId?: string;
  branchId?: string;
  newChatId?: string;
  error?: string;
};

export function reportContextBranchForkDiag(diag: ContextBranchForkDiag): void {
  if (typeof window === 'undefined') {
    return;
  }
  (window as Window & { __MYRM_CONTEXT_BRANCH_FORK_DIAG__?: ContextBranchForkDiag }).__MYRM_CONTEXT_BRANCH_FORK_DIAG__ =
    diag;
}

export function bookmarkDisplayLabel(record: ContextBranchRecord): string {
  const label = record.label.trim();
  if (label) {
    return label;
  }
  const segments = record.snapshot_path.split(/[/\\]/);
  return segments[segments.length - 1] || record.snapshot_path;
}

export function useCompactedSummaryState() {
  const router = useRouter();

  const {
    chatId,
    compactedSummary,
    setCompactedSummary,
    lastCompactionMeta,
    contextBranches,
    setContextBranches,
    contextBranchesLoadError,
    setContextBranchesLoadError,
  } = useChatStore(
    useShallow((state) => ({
      chatId: state.chatId,
      compactedSummary: state.compactedSummary,
      setCompactedSummary: state.setCompactedSummary,
      lastCompactionMeta: state.lastCompactionMeta,
      contextBranches: state.contextBranches,
      setContextBranches: state.setContextBranches,
      contextBranchesLoadError: state.contextBranchesLoadError,
      setContextBranchesLoadError: state.setContextBranchesLoadError,
    })),
  );

  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [isSavingBookmark, setIsSavingBookmark] = useState(false);
  const [forkingBranchId, setForkingBranchId] = useState<string | null>(null);

  const [isArchiveOpen, setIsArchiveOpen] = useState(false);
  const [archiveMessages, setArchiveMessages] = useState<Message[]>([]);
  const [isLoadingArchive, setIsLoadingArchive] = useState(false);
  const [bookmarksLoading, setBookmarksLoading] = useState(false);

  const bookmarks = useMemo(() => contextBranches.slice(-MAX_BOOKMARKS_DISPLAY).reverse(), [contextBranches]);

  const loadBookmarks = useCallback(async (): Promise<ContextBranchRecord[]> => {
    const requestChatId = chatId;
    if (!requestChatId) {
      setContextBranches([]);
      setContextBranchesLoadError(null);
      return [];
    }
    setBookmarksLoading(true);
    try {
      const branches = await listContextBranches(requestChatId);
      if (useChatStore.getState().chatId !== requestChatId) {
        return [];
      }
      setContextBranches(branches);
      setContextBranchesLoadError(null);
      return branches.slice(-MAX_BOOKMARKS_DISPLAY).reverse();
    } catch (err) {
      console.error('[CompactedSummaryView] failed to load bookmarks', err);
      if (useChatStore.getState().chatId === requestChatId) {
        setContextBranchesLoadError('load_failed');
      }
      return [];
    } finally {
      if (useChatStore.getState().chatId === requestChatId) {
        setBookmarksLoading(false);
      }
    }
  }, [chatId, setContextBranches, setContextBranchesLoadError]);

  const handleEdit = useCallback(() => {
    if (!compactedSummary) {
      return;
    }
    setEditValue(compactedSummary);
    setIsEditing(true);
  }, [compactedSummary]);

  const handleCancel = useCallback(() => {
    setIsEditing(false);
  }, []);

  const handleSave = useCallback(async () => {
    if (!chatId) {
      return;
    }
    setIsSaving(true);
    try {
      await updateCompactionSummary(chatId, editValue);
      setCompactedSummary(editValue);
      setIsEditing(false);
    } catch (err) {
      console.error('[CompactedSummaryView] failed to save summary', err);
    } finally {
      setIsSaving(false);
    }
  }, [chatId, editValue, setCompactedSummary]);

  const handleViewArchive = useCallback(async () => {
    setIsArchiveOpen(true);
    if (!chatId || archiveMessages.length > 0) {
      return;
    }

    setIsLoadingArchive(true);
    try {
      const res = await getChatArchive(chatId);
      setArchiveMessages(res.messages || []);
    } catch (err) {
      console.error('[CompactedSummaryView] failed to fetch archive', err);
    } finally {
      setIsLoadingArchive(false);
    }
  }, [chatId, archiveMessages.length]);

  const handleSaveBookmark = useCallback(async () => {
    const snapshotPath = lastCompactionMeta?.snapshotPath;
    if (!chatId || !snapshotPath || isSavingBookmark) {
      return;
    }
    setIsSavingBookmark(true);
    try {
      await createContextBranch(chatId, { snapshot_path: snapshotPath });
      await loadBookmarks();
      showI18nToast('chat.compactedSummary.bookmarkSaved', undefined, { type: 'success' });
    } catch (err) {
      console.error('[CompactedSummaryView] failed to save bookmark', err);
      showI18nToast('chat.compactedSummary.bookmarkSaveFailed', undefined, { type: 'error' });
    } finally {
      setIsSavingBookmark(false);
    }
  }, [chatId, lastCompactionMeta?.snapshotPath, isSavingBookmark, loadBookmarks]);

  const navigateToForkedChat = useCallback(
    (newChatId: string) => {
      const target = `/${newChatId}`;
      router.push(target);
      if (typeof window !== 'undefined' && resolveE2eApiBase()) {
        window.location.assign(target);
      }
    },
    [router],
  );

  const handleForkFromBookmark = useCallback(
    async (bookmark: ContextBranchRecord) => {
      if (!chatId || forkingBranchId) {
        return;
      }
      if (useChatStore.getState().loading) {
        reportContextBranchForkDiag({
          phase: 'blocked-loading',
          at: Date.now(),
          chatId,
          branchId: bookmark.branch_id,
        });
        showI18nToast('chat.fork.streamingBlocked', undefined, { type: 'error' });
        return;
      }
      setForkingBranchId(bookmark.branch_id);
      reportContextBranchForkDiag({
        phase: 'start',
        at: Date.now(),
        chatId,
        branchId: bookmark.branch_id,
      });
      try {
        const result = await forkContextBranch(chatId, bookmark.branch_id, bookmarkDisplayLabel(bookmark));
        if (!result.new_chat_id) {
          throw new Error('Fork response missing new_chat_id');
        }
        reportContextBranchForkDiag({
          phase: 'api-ok',
          at: Date.now(),
          chatId,
          branchId: bookmark.branch_id,
          newChatId: result.new_chat_id,
        });
        useWorkspaceStore.getState().addPane(result.new_chat_id);
        navigateToForkedChat(result.new_chat_id);
        reportContextBranchForkDiag({
          phase: 'navigate',
          at: Date.now(),
          chatId,
          branchId: bookmark.branch_id,
          newChatId: result.new_chat_id,
        });
        showI18nToast('chat.compactedSummary.bookmarkForkSuccess', undefined, { type: 'success' });
      } catch (err) {
        reportContextBranchForkDiag({
          phase: 'api-error',
          at: Date.now(),
          chatId,
          branchId: bookmark.branch_id,
          error: err instanceof Error ? err.message : String(err),
        });
        console.error('[CompactedSummaryView] failed to fork from bookmark', err);
        showI18nToast('chat.compactedSummary.bookmarkForkFailed', undefined, { type: 'error' });
      } finally {
        setForkingBranchId(null);
      }
    },
    [chatId, forkingBranchId, navigateToForkedChat],
  );

  return {
    chatId,
    compactedSummary,
    lastCompactionMeta,
    contextBranchesLoadError,
    bookmarks,
    bookmarksLoading,
    forkingBranchId,
    isEditing,
    editValue,
    setEditValue,
    isSaving,
    isSavingBookmark,
    isArchiveOpen,
    setIsArchiveOpen,
    archiveMessages,
    isLoadingArchive,
    handleEdit,
    handleCancel,
    handleSave,
    handleViewArchive,
    handleSaveBookmark,
    handleForkFromBookmark,
    loadBookmarks,
  };
}
