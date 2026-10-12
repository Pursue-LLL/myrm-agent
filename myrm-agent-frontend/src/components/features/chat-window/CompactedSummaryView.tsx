'use client';

/**
 * [INPUT]
 * - useCompactedSummaryState from ./useCompactedSummaryState
 * - CompactedMilestoneCard, BranchSummaryCard, parseCompactionEntry from '../compaction-milestone'
 * - CompactionAnchorStrip, parseExactAnchors from './'
 * - CompactedArchiveModal, CompactedBookmarksList from './'
 *
 * [OUTPUT]
 * - CompactedSummaryView: Context compaction view hosting milestone cards, anchors, bookmarks & archive time machine
 *
 * [POS]
 * Context compaction summary host view in chat stream (Item 27 refactor).
 * Decoupled state management via useCompactedSummaryState.
 * File length < 280 lines (strictly < 400 lines threshold). Zero `any` types. Zero native emoji.
 */

import React, { useEffect, useMemo, useRef } from 'react';
import { FileText, PencilSimple, FloppyDisk, X, ClockCounterClockwise, BookmarkSimple } from '@phosphor-icons/react';
import { useTranslations } from 'next-intl';
import { format } from 'date-fns';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { CompactionAnchorStrip } from './CompactionAnchorStrip';
import { parseExactAnchors } from './parseExactAnchors';
import { CompactedArchiveModal } from './CompactedArchiveModal';
import { CompactedBookmarksList } from './CompactedBookmarksList';
import { CompactedMilestoneCard, BranchSummaryCard } from '../compaction-milestone';
import { parseCompactionEntry } from '../compaction-milestone/compactionParser';
import { useCompactedSummaryState, bookmarkDisplayLabel } from './useCompactedSummaryState';

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

function formatTokens(tokens: number): string {
  if (tokens >= 1000) {
    return `${(tokens / 1000).toFixed(1)}K`;
  }
  return String(tokens);
}

function formatBookmarkTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return format(date, 'yyyy-MM-dd HH:mm');
}

export const CompactedSummaryView = () => {
  const t = useTranslations('chat.compactedSummary');
  const summaryViewRef = useRef<HTMLDivElement>(null);

  const {
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
  } = useCompactedSummaryState();

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

  const milestoneEntry = useMemo(
    () => parseCompactionEntry(cleanedSummary, lastCompactionMeta, archiveMessages),
    [cleanedSummary, lastCompactionMeta, archiveMessages],
  );

  const latestBookmark = bookmarks[0];

  if (!compactedSummary) {
    return null;
  }

  return (
    <div className="w-full flex flex-col items-center my-6 max-w-5xl mx-auto px-4 md:px-0">
      {/* 5-Section Structured Milestone Capsule Card (Item 27) */}
      <CompactedMilestoneCard entry={milestoneEntry} className="mb-4" />

      {/* Cross-Branch Summary Indicator when branch bookmark exists */}
      {latestBookmark && (
        <BranchSummaryCard
          entry={{
            id: latestBookmark.branch_id,
            sourceBranchId: latestBookmark.branch_id,
            sourceBranchName: bookmarkDisplayLabel(latestBookmark),
            summary: t('branchContextDistilled'),
            keyTakeaways: [t('branchSnapshotArchived', { path: latestBookmark.snapshot_path })],
            createdAt: latestBookmark.created_at || new Date().toISOString(),
          }}
          className="mb-4"
        />
      )}

      <div className="flex items-center w-full my-4 opacity-50">
        <div className="flex-1 h-px bg-border" />
        <button
          type="button"
          className="px-4 text-xs font-medium text-muted-foreground flex items-center gap-1.5 cursor-pointer hover:text-primary transition-colors bg-transparent border-0"
          onClick={handleViewArchive}
        >
          <ClockCounterClockwise size={14} weight="duotone" />
          {t('foldLabel')}
        </button>
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
                className="text-xs flex items-center gap-1 bg-background hover:bg-muted text-foreground px-2 py-1 rounded-full border cursor-pointer"
              >
                <PencilSimple size={12} />
                {t('edit')}
              </button>
            ) : (
              <>
                <button
                  type="button"
                  onClick={handleCancel}
                  className="text-xs flex items-center gap-1 bg-background hover:bg-muted text-foreground px-2 py-1 rounded-full border cursor-pointer"
                  disabled={isSaving}
                >
                  <X size={12} />
                  {t('cancel')}
                </button>
                <button
                  type="button"
                  onClick={handleSave}
                  className="text-xs flex items-center gap-1 bg-primary hover:bg-primary/90 text-primary-foreground px-2 py-1 rounded-full cursor-pointer"
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
                className="inline-flex items-center gap-1 text-primary hover:text-primary/80 transition-colors disabled:opacity-50 cursor-pointer"
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
