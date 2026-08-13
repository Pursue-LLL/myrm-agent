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
  const { chatId, compactedSummary, setCompactedSummary, lastCompactionMeta, contextBranches, setContextBranches, contextBranchesLoadError, setContextBranchesLoadError } =
    useChatStore(
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

  const bookmarks = useMemo(
    () => contextBranches.slice(-MAX_BOOKMARKS_DISPLAY).reverse(),
    [contextBranches],
  );

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
    if (!compactedSummary) {return;}
    setEditValue(compactedSummary);
    setIsEditing(true);
  };

  const handleCancel = () => {
    setIsEditing(false);
  };

  const handleSave = async () => {
    if (!chatId) {return;}
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
    if (!chatId || archiveMessages.length > 0) {return;}

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
    if (!chatId || !snapshotPath || isSavingBookmark) {return;}
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

  const handleForkFromBookmark = useCallback(async (bookmark: ContextBranchRecord) => {
    if (!chatId || forkingBranchId) {return;}
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
  }, [chatId, forkingBranchId, router]);

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
              {compactedSummary}
            </ReactMarkdown>
          </div>
        )}

        {(lastCompactionMeta?.tokensSaved ?? 0) > 0 && (
          <div className="mt-3 pt-3 border-t border-border/50 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
            <span>{t('tokensSaved', { tokens: formatTokens(lastCompactionMeta!.tokensSaved) })}</span>
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

        <div
          data-testid="compacted-summary-bookmarks"
          data-bookmarks-state={
            bookmarksLoading
              ? 'loading'
              : contextBranchesLoadError
                ? 'error'
                : bookmarks.length === 0
                  ? 'empty'
                  : 'ready'
          }
          className="mt-3 pt-3 border-t border-border/50 flex flex-col gap-1.5"
        >
          <span className="text-[10px] font-medium text-muted-foreground">{t('bookmarksTitle')}</span>
          {bookmarksLoading ? (
            <span className="text-[10px] text-muted-foreground">{t('bookmarksLoading')}</span>
          ) : contextBranchesLoadError ? (
            <div className="flex items-center gap-2 text-[10px]">
              <span className="text-rose-600 dark:text-rose-400">{t('bookmarksLoadError')}</span>
              <button
                type="button"
                onClick={() => void loadBookmarks()}
                className="text-primary hover:text-primary/80 transition-colors"
              >
                {t('bookmarksRetry')}
              </button>
            </div>
          ) : bookmarks.length === 0 ? (
            <span className="text-[10px] text-muted-foreground">{t('bookmarksEmpty')}</span>
          ) : (
            <ul className="flex flex-col gap-1 max-h-28 overflow-y-auto">
              {bookmarks.map((bookmark) => {
                const bookmarkTime = formatBookmarkTime(bookmark.created_at);
                const isForking = forkingBranchId === bookmark.branch_id;
                return (
                  <li
                    key={bookmark.branch_id}
                    data-testid="compacted-summary-bookmark-item"
                    className="flex flex-col gap-0.5 sm:flex-row sm:items-center sm:gap-2 text-[10px] text-foreground/80 min-w-0"
                    title={bookmark.snapshot_path}
                  >
                    <div className="flex items-center gap-1 min-w-0 flex-1">
                      <BookmarkSimple size={10} weight="duotone" className="shrink-0 text-primary/70" />
                      <span className="truncate">{bookmarkDisplayLabel(bookmark)}</span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0 sm:ml-auto">
                      {bookmarkTime ? (
                        <span className="tabular-nums text-muted-foreground">{bookmarkTime}</span>
                      ) : null}
                      <button
                        type="button"
                        data-testid="compacted-summary-bookmark-fork"
                        data-branch-id={bookmark.branch_id}
                        disabled={isForking}
                        className="text-primary hover:text-primary/80 transition-colors disabled:opacity-50"
                      >
                        {isForking ? t('bookmarkForking') : t('bookmarkFork')}
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>

      {isArchiveOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-background/80 backdrop-blur-sm p-4 md:p-8">
          <div className="bg-background border shadow-xl rounded-xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden">
            <div className="p-4 border-b flex items-center justify-between bg-muted/30">
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <ClockCounterClockwise size={20} weight="duotone" />
                {t('archiveTitle')}
              </h2>
              <button type="button" onClick={() => setIsArchiveOpen(false)} className="p-2 hover:bg-muted rounded-full">
                <X size={20} />
              </button>
            </div>

            <div className="p-6 overflow-y-auto flex-1 space-y-6">
              {isLoadingArchive ? (
                <div className="flex justify-center p-8">
                  <div className="w-8 h-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
                </div>
              ) : archiveMessages.length === 0 ? (
                <div className="text-center text-muted-foreground p-8">{t('archiveEmpty')}</div>
              ) : (
                archiveMessages.map((msg, idx) => (
                  <div
                    key={msg.messageId || idx}
                    className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
                  >
                    <div className="text-xs text-muted-foreground mb-1">
                      {msg.role === 'user' ? t('roleUser') : t('roleAssistant')} •{' '}
                      {msg.createdAt ? format(new Date(msg.createdAt), 'yyyy-MM-dd HH:mm:ss') : ''}
                    </div>
                    <div
                      className={`prose dark:prose-invert prose-sm break-words w-full max-w-[85%] rounded-2xl px-4 py-3 text-sm ${
                        msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground'
                      }`}
                    >
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm, remarkMath]}
                        rehypePlugins={[rehypeKatex]}
                        components={markdownLinkComponents}
                      >
                        {msg.content || ''}
                      </ReactMarkdown>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
