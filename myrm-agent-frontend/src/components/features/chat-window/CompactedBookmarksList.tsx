'use client';

/**
 * Context compaction branch bookmarks list and quick fork controls.
 *
 * [INPUT]
 * - bookmarks: ContextBranchRecord list (POS: Context branch snapshot records)
 * - onRetryLoad: Reload callback
 * - labels: Translated localized string labels
 *
 * [OUTPUT]
 * - CompactedBookmarksList: Rendered list of context snapshot bookmarks with fork triggers
 *
 * [POS]
 * Presentation layer component managing compaction snapshot bookmarks display and fork action delegation.
 */

import React from 'react';
import { BookmarkSimple } from '@phosphor-icons/react';
import type { ContextBranchRecord } from '@/services/chat';

export interface CompactedBookmarksListProps {
  bookmarks: ContextBranchRecord[];
  bookmarksLoading: boolean;
  contextBranchesLoadError: string | null;
  forkingBranchId: string | null;
  onRetryLoad: () => void;
  formatBookmarkTime: (iso: string) => string;
  bookmarkDisplayLabel: (record: ContextBranchRecord) => string;
  labels: {
    bookmarksTitle: string;
    bookmarksLoading: string;
    bookmarksLoadError: string;
    bookmarksRetry: string;
    bookmarksEmpty: string;
    bookmarkForking: string;
    bookmarkFork: string;
  };
}

export function CompactedBookmarksList({
  bookmarks,
  bookmarksLoading,
  contextBranchesLoadError,
  forkingBranchId,
  onRetryLoad,
  formatBookmarkTime,
  bookmarkDisplayLabel,
  labels,
}: CompactedBookmarksListProps) {
  return (
    <div
      data-testid="compacted-summary-bookmarks"
      data-bookmarks-state={
        bookmarksLoading ? 'loading' : contextBranchesLoadError ? 'error' : bookmarks.length === 0 ? 'empty' : 'ready'
      }
      className="mt-3 pt-3 border-t border-border/50 flex flex-col gap-1.5"
    >
      <span className="text-[10px] font-medium text-muted-foreground">{labels.bookmarksTitle}</span>
      {bookmarksLoading ? (
        <span className="text-[10px] text-muted-foreground">{labels.bookmarksLoading}</span>
      ) : contextBranchesLoadError ? (
        <div className="flex items-center gap-2 text-[10px]">
          <span className="text-rose-600 dark:text-rose-400">{labels.bookmarksLoadError}</span>
          <button type="button" onClick={onRetryLoad} className="text-primary hover:text-primary/80 transition-colors">
            {labels.bookmarksRetry}
          </button>
        </div>
      ) : bookmarks.length === 0 ? (
        <span className="text-[10px] text-muted-foreground">{labels.bookmarksEmpty}</span>
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
                  {bookmarkTime ? <span className="tabular-nums text-muted-foreground">{bookmarkTime}</span> : null}
                  <button
                    type="button"
                    data-testid="compacted-summary-bookmark-fork"
                    data-branch-id={bookmark.branch_id}
                    disabled={isForking}
                    className="text-primary hover:text-primary/80 transition-colors disabled:opacity-50"
                  >
                    {isForking ? labels.bookmarkForking : labels.bookmarkFork}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
