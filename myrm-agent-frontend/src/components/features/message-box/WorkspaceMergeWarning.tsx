'use client';

/**
 * [INPUT]
 * @/store/chat/types::WorkspaceMergeFailure
 *
 * [OUTPUT]
 * WorkspaceMergeWarning: Per-turn collapsible panel for workspace merge failures.
 *
 * [POS]
 * Surfaces ISOLATED_COPY merge errors without requiring users to inspect delegate tool JSON.
 */

import React, { useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { WorkspaceMergeFailure } from '@/store/chat/types';

interface WorkspaceMergeWarningProps {
  failures: WorkspaceMergeFailure[];
  failedCount?: number;
  truncated?: number;
}

export function WorkspaceMergeWarning({ failures, failedCount, truncated }: WorkspaceMergeWarningProps) {
  const [expanded, setExpanded] = useState(false);
  const t = useTranslations('chat');

  if (!failures.length) return null;

  const totalCount = failedCount && failedCount > failures.length ? failedCount : failures.length;
  const hiddenCount = truncated && truncated > 0
    ? truncated
    : failedCount && failedCount > failures.length
      ? failedCount - failures.length
      : 0;

  return (
    <div
      data-testid="workspace-merge-warning"
      className="mt-2 border border-amber-300/60 dark:border-amber-700/50 rounded-lg overflow-hidden bg-amber-50/80 dark:bg-amber-950/20"
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full px-3 py-2 text-sm text-left hover:bg-amber-100/50 dark:hover:bg-amber-900/20 transition-colors"
      >
        <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
        <span className="font-medium text-amber-800 dark:text-amber-200">
          {t('message.workspaceMergeFailedTitle')}
        </span>
        <span className="text-amber-600 dark:text-amber-400 text-xs ml-auto mr-1">
          {t('message.workspaceMergeFailed', { count: totalCount })}
        </span>
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-amber-500 shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-amber-500 shrink-0" />
        )}
      </button>

      {expanded && (
        <div className="px-3 pb-2 space-y-1.5">
          {failures.map((failure, index) => (
            <div
              key={`${failure.message}-${index}`}
              className="px-2 py-1.5 rounded bg-amber-100/60 dark:bg-amber-900/20 text-xs text-amber-900 dark:text-amber-100 break-all"
            >
              {failure.message}
            </div>
          ))}
          {hiddenCount > 0 && (
            <p className="px-2 py-1 text-xs text-amber-700/80 dark:text-amber-300/80">
              {t('message.workspaceMergeFailedMore', { count: hiddenCount })}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
