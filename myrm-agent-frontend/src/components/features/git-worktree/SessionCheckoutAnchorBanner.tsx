'use client';

/**
 * Session Checkout Anchor Banner.
 *
 * [INPUT] useWorktreeStore, lucide-react, next-intl
 * [OUTPUT] SessionCheckoutAnchorBanner: Smart warning bar when current session worktree differs from active worktree.
 * [POS] src/components/features/git-worktree/SessionCheckoutAnchorBanner.tsx
 */

import { memo, useState, useCallback, useEffect } from 'react';
import {
  GitFork,
  ArrowRightLeft,
  FileCode2,
  CheckCircle2,
  AlertTriangle,
  Loader2,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { useWorktreeStore } from './useWorktreeStore';
import { SessionTouchedFilesPopover } from './SessionTouchedFilesPopover';

export interface SessionCheckoutAnchorBannerProps {
  sessionId: string;
  className?: string;
  onSwitched?: (newWorktreePath: string) => void;
}

export const SessionCheckoutAnchorBanner = memo(function SessionCheckoutAnchorBanner({
  sessionId,
  className,
  onSwitched,
}: SessionCheckoutAnchorBannerProps) {
  const t = useTranslations('gitWorktree');
  const {
    activeWorktree,
    currentSessionAnchor,
    checkSessionAnchor,
    syncSessionToAnchor,
  } = useWorktreeStore();

  const [isSyncing, setIsSyncing] = useState(false);
  const [showTouchedFiles, setShowTouchedFiles] = useState(false);

  useEffect(() => {
    if (sessionId) {
      checkSessionAnchor(sessionId);
    }
  }, [sessionId, checkSessionAnchor]);

  const handleSync = useCallback(async () => {
    if (!sessionId) {
      return;
    }
    setIsSyncing(true);
    try {
      await syncSessionToAnchor(sessionId);
      if (currentSessionAnchor?.worktree_path && onSwitched) {
        onSwitched(currentSessionAnchor.worktree_path);
      }
    } finally {
      setIsSyncing(false);
    }
  }, [sessionId, syncSessionToAnchor, currentSessionAnchor, onSwitched]);

  if (!currentSessionAnchor || currentSessionAnchor.session_id !== sessionId) {
    return null;
  }

  const isAnchored = currentSessionAnchor.is_anchored;
  const sessionBranch = currentSessionAnchor.checkout_ref || 'unknown';
  const activeBranch = activeWorktree?.branch || 'main';
  const touchedCount = currentSessionAnchor.touched_files?.length || 0;

  if (isAnchored) {
    return (
      <div
        className={cn(
          'flex items-center justify-between px-3 py-1.5 rounded-lg border text-xs',
          'bg-emerald-500/10 border-emerald-500/20 text-emerald-700 dark:text-emerald-400',
          className,
        )}
        data-testid="session-checkout-anchor-synced"
      >
        <div className="flex items-center gap-1.5 min-w-0">
          <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0 text-emerald-500" />
          <span className="truncate">
            {t('syncedHint', { branch: sessionBranch }) || `Workspace anchored to ${sessionBranch}`}
          </span>
        </div>

        {touchedCount > 0 && (
          <button
            type="button"
            onClick={() => {
              setShowTouchedFiles(true);
            }}
            className="flex items-center gap-1 font-mono text-[11px] underline hover:opacity-80 ml-2 flex-shrink-0"
          >
            <FileCode2 className="h-3 w-3" />
            <span>{touchedCount} {t('touchedFiles') || 'files'}</span>
          </button>
        )}

        {showTouchedFiles && (
          <SessionTouchedFilesPopover
            touchedFiles={currentSessionAnchor.touched_files}
            onClose={() => {
              setShowTouchedFiles(false);
            }}
          />
        )}
      </div>
    );
  }

  return (
    <div
      className={cn(
        'flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 p-2.5 rounded-lg border text-xs',
        'bg-amber-500/10 border-amber-500/30 text-amber-900 dark:text-amber-200',
        className,
      )}
      data-testid="session-checkout-anchor-unanchored"
    >
      <div className="flex items-start sm:items-center gap-2 min-w-0">
        <AlertTriangle className="h-4 w-4 flex-shrink-0 text-amber-600 dark:text-amber-400 mt-0.5 sm:mt-0" />
        <div className="leading-snug truncate">
          <span className="font-semibold">{t('worktreeMismatch') || 'Worktree Mismatch'}: </span>
          <span>
            {t('mismatchDesc', {
              sessionBranch,
              activeBranch,
            }) || `Created on ${sessionBranch}, active is ${activeBranch}`}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-1.5 flex-shrink-0 self-end sm:self-auto">
        {touchedCount > 0 && (
          <button
            type="button"
            onClick={() => {
              setShowTouchedFiles(true);
            }}
            className={cn(
              'px-2 py-1 rounded text-[11px] font-medium border border-amber-500/30 hover:bg-amber-500/20',
              'flex items-center gap-1 transition-colors',
            )}
          >
            <FileCode2 className="h-3 w-3" />
            <span>{touchedCount}</span>
          </button>
        )}

        <button
          type="button"
          onClick={handleSync}
          disabled={isSyncing}
          className={cn(
            'px-2.5 py-1 rounded-md text-[11px] font-semibold bg-amber-600 text-white dark:bg-amber-500 dark:text-slate-950',
            'hover:opacity-90 active:scale-98 transition-all flex items-center gap-1 shadow-sm',
          )}
        >
          {isSyncing ? (
            <>
              <Loader2 className="h-3 w-3 animate-spin" />
              <span>{t('switching') || 'Switching...'}</span>
            </>
          ) : (
            <>
              <ArrowRightLeft className="h-3 w-3" />
              <span>{t('switchBack') || 'Align Worktree'}</span>
            </>
          )}
        </button>
      </div>

      {showTouchedFiles && (
        <SessionTouchedFilesPopover
          touchedFiles={currentSessionAnchor.touched_files}
          onClose={() => {
            setShowTouchedFiles(false);
          }}
        />
      )}
    </div>
  );
});
