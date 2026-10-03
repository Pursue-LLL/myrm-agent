'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import useChatStore from '@/store/useChatStore';
import useWorkspaceStore from '@/store/useWorkspaceStore';
import { useShallow } from 'zustand/react/shallow';
import { FileText, PencilSimple, FloppyDisk, X, ClockCounterClockwise, BookmarkSimple } from '@phosphor-icons/react';
import { useTranslations } from 'next-intl';
import {
  createContextBranch,
  forkContextBranch,
  getChatArchive,
  listContextBranches,
  updateCompactionSummary,
  type ContextBranchRecord,
} from '@/services/chat';
import type { Message } from '@/store/chat/types';
import { format } from 'date-fns';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { showI18nToast } from '@/services/i18nToastService';
import { resolveE2eApiBase } from '@/lib/deploy-mode';
import { CompactionAnchorStrip } from './CompactionAnchorStrip';
import { parseExactAnchors } from './parseExactAnchors';
import { CompactedArchiveModal } from './CompactedArchiveModal';
import { CompactedBookmarksList } from './CompactedBookmarksList';

const markdownLinkComponents = {
  a: ({ href, children }: { href?: string; children?: React.ReactNode }) => {
    const isExternal = href && /^https?:\/\//.test(href);
    if (isExternal) {
      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary underline hover:text-primary/80"
        >
          {children}
        </a>
      );
    }
    return <a href={href}>{children}</a>;
  },
};

const MAX_BOOKMARKS_DISPLAY = 5;

function formatTokens(tokens: number): string {
  if (tokens >= 1000) {
    return `${(tokens / 1000).toFixed(1)}K`;
  }
  return String(tokens);
}

function bookmarkDisplayLabel(record: ContextBranchRecord): string {
  const label = record.label.trim();
  if (label) {
    return label;
  }
  const segments = record.snapshot_path.split(/[/\\]/);
  return segments[segments.length - 1] || record.snapshot_path;
}

function formatBookmarkTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return format(date, 'yyyy-MM-dd HH:mm');
}

type ContextBranchForkDiag = {
  phase: string;
  at: number;
  chatId?: string;
  branchId?: string;
  newChatId?: string;
  error?: string;
};

function reportContextBranchForkDiag(diag: ContextBranchForkDiag): void {
  if (typeof window === 'undefined') {
    return;
  }
  (window as Window & { __MYRM_CONTEXT_BRANCH_FORK_DIAG__?: ContextBranchForkDiag }).__MYRM_CONTEXT_BRANCH_FORK_DIAG__ =
    diag;
}

export const CompactedSummaryView = () => {
  const router = useRouter();
  const t = useTranslations('chat.compactedSummary');
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
  const summaryViewRef = useRef<HTMLDivElement>(null);

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

  const handleEdit = () => {
    if (!compactedSummary) {
      return;
    }
    setEditValue(compactedSummary);
    setIsEditing(true);
  };

  const handleCancel = () => {
    setIsEditing(false);
  };

  const handleSave = async () => {
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
  };

  const handleViewArchive = async () => {
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
  };

  const handleSaveBookmark = async () => {
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
  };

  const navigateToForkedChat = (newChatId: string) => {
    const target = `/${newChatId}`;
    router.push(target);
    // SHPOIB Chrome E2E: soft navigation can lag behind CDP pathname probes; hard nav is SSOT there.
    if (typeof window !== 'undefined' && resolveE2eApiBase()) {
      window.location.assign(target);
    }
  };

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
    [chatId, forkingBranchId, router],
  );

  useEffect(() => {
    const root = summaryViewRef.current;
    if (!root) {
      return undefined;
    }
    const onNativeClick = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) {
        return;
      }
      const forkBtn = target.closest('[data-testid="compacted-summary-bookmark-fork"]');
      if (!forkBtn || forkBtn.hasAttribute('disabled')) {
        return;
      }
      const branchId = forkBtn.getAttribute('data-branch-id');
      if (!branchId) {
        return;
      }
      const bookmark = bookmarks.find((item) => item.branch_id === branchId);
      if (!bookmark) {
        return;
      }
      event.preventDefault();
      void handleForkFromBookmark(bookmark);
    };
    root.addEventListener('click', onNativeClick);
    return () => root.removeEventListener('click', onNativeClick);
  }, [bookmarks, handleForkFromBookmark]);

  const { anchors, cleanedSummary } = useMemo(
    () => parseExactAnchors(compactedSummary || '', lastCompactionMeta?.exactAnchors),
    [compactedSummary, lastCompactionMeta],
  );

  if (!compactedSummary) {
    return null;
  }

  return (
    <div className="w-full flex flex-col items-center my-6 max-w-5xl mx-auto px-4 md:px-0">
      <div className="flex items-center w-full my-4 opacity-50">
        <div className="flex-1 h-px bg-border" />
        <span
          role="button"
          tabIndex={0}
          className="px-4 text-xs font-medium text-muted-foreground flex items-center gap-1.5 cursor-pointer hover:text-primary transition-colors"
          onClick={handleViewArchive}
          onKeyDown={(event) => event.key === 'Enter' && handleViewArchive()}
        >
          <ClockCounterClockwise size={14} weight="duotone" />
          {t('foldLabel')}
        </span>
        <div className="flex-1 h-px bg-border" />
      </div>

      <div
        ref={summaryViewRef}
        className="w-full relative group rounded-xl border border-primary/20 bg-primary/5 p-4 backdrop-blur-sm transition-all hover:border-primary/40"
      >
        <div className="flex items-center justify-between mb-3 gap-2 flex-wrap">
          <div className="flex items-center gap-2 text-sm font-semibold text-primary">
            <FileText size={16} weight="duotone" />
            {t('title')}
          </div>
          <div className="flex gap-2 opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity">
            {!isEditing ? (
              <button
                type="button"
                onClick={handleEdit}
                className="text-xs flex items-center gap-1 bg-background hover:bg-muted text-foreground px-2 py-1 rounded-full border"
              >
                <PencilSimple size={12} />
                {t('edit')}
              </button>
            ) : (
              <>
                <button
                  type="button"
                  onClick={handleCancel}
                  className="text-xs flex items-center gap-1 bg-background hover:bg-muted text-foreground px-2 py-1 rounded-full border"
                  disabled={isSaving}
                >
                  <X size={12} />
                  {t('cancel')}
                </button>
                <button
                  type="button"
                  onClick={handleSave}
                  className="text-xs flex items-center gap-1 bg-primary hover:bg-primary/90 text-primary-foreground px-2 py-1 rounded-full"
                  disabled={isSaving}
                >
                  {isSaving ? (
                    <div className="w-3 h-3 animate-spin rounded-full border-2 border-background border-t-transparent" />
                  ) : (
                    <FloppyDisk size={12} />
                  )}
                  {t('save')}
                </button>
              </>
            )}
          </div>
        </div>

        {!isEditing && <CompactionAnchorStrip anchors={anchors} className="mb-3" />}

        {isEditing ? (
          <textarea
            value={editValue}
            onChange={(event) => setEditValue(event.target.value)}
            className="w-full min-h-[200px] text-sm bg-background border rounded-lg p-3 focus:outline-none focus:ring-1 focus:ring-primary font-mono resize-y"
          />
        ) : (
          <div className="prose dark:prose-invert prose-sm max-w-none break-words text-sm text-foreground/80 whitespace-pre-wrap max-h-[300px] overflow-y-auto scrollbar-thin">
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkMath]}
              rehypePlugins={[rehypeKatex]}
              components={markdownLinkComponents}
            >
              {cleanedSummary}
            </ReactMarkdown>
          </div>
        )}

        {lastCompactionMeta && (lastCompactionMeta.tokensSaved ?? 0) > 0 && (
          <div className="mt-3 pt-3 border-t border-border/50 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
            <span>{t('tokensSaved', { tokens: formatTokens(lastCompactionMeta.tokensSaved ?? 0) })}</span>
            {lastCompactionMeta?.snapshotPath && (
              <button
                type="button"
                disabled={isSavingBookmark}
                onClick={handleSaveBookmark}
                className="inline-flex items-center gap-1 text-primary hover:text-primary/80 transition-colors disabled:opacity-50"
              >
                <BookmarkSimple size={12} weight="duotone" />
                {isSavingBookmark ? t('savingBookmark') : t('saveBookmark')}
              </button>
            )}
          </div>
        )}

        <CompactedBookmarksList
          bookmarks={bookmarks}
          bookmarksLoading={bookmarksLoading}
          contextBranchesLoadError={contextBranchesLoadError}
          forkingBranchId={forkingBranchId}
          onRetryLoad={() => void loadBookmarks()}
          formatBookmarkTime={formatBookmarkTime}
          bookmarkDisplayLabel={bookmarkDisplayLabel}
          labels={{
            bookmarksTitle: t('bookmarksTitle'),
            bookmarksLoading: t('bookmarksLoading'),
            bookmarksLoadError: t('bookmarksLoadError'),
            bookmarksRetry: t('bookmarksRetry'),
            bookmarksEmpty: t('bookmarksEmpty'),
            bookmarkForking: t('bookmarkForking'),
            bookmarkFork: t('bookmarkFork'),
          }}
        />
      </div>

      <CompactedArchiveModal
        isOpen={isArchiveOpen}
        isLoading={isLoadingArchive}
        messages={archiveMessages}
        title={t('archiveTitle')}
        emptyLabel={t('archiveEmpty')}
        roleUserLabel={t('roleUser')}
        roleAssistantLabel={t('roleAssistant')}
        onClose={() => setIsArchiveOpen(false)}
        markdownLinkComponents={markdownLinkComponents}
      />
    </div>
  );
};
