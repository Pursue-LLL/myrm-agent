'use client';

/**
 * [INPUT]
 * @/store/chat/types::FileMutationFailure
 *
 * [OUTPUT]
 * FileMutationWarning: Per-turn warning banner for failed file mutations.
 *
 * [POS]
 * Displays a collapsible warning panel when agent file edits fail and are rolled back,
 * preventing the user from mistaking AI claims of success for actual disk changes.
 */

import React, { useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { FileMutationFailure } from '@/store/chat/types';

interface FileMutationWarningProps {
  failures: FileMutationFailure[];
}

function shortenPath(fullPath: string): string {
  const parts = fullPath.split('/');
  if (parts.length <= 3) return fullPath;
  return `…/${parts.slice(-2).join('/')}`;
}

export function FileMutationWarning({ failures }: FileMutationWarningProps) {
  const [expanded, setExpanded] = useState(false);
  const t = useTranslations('chat');

  if (!failures.length) return null;

  return (
    <div className="mt-2 border border-amber-300/60 dark:border-amber-700/50 rounded-lg overflow-hidden bg-amber-50/80 dark:bg-amber-950/20">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full px-3 py-2 text-sm text-left hover:bg-amber-100/50 dark:hover:bg-amber-900/20 transition-colors"
      >
        <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
        <span className="font-medium text-amber-800 dark:text-amber-200">{t('message.fileMutationFailedTitle')}</span>
        <span className="text-amber-600 dark:text-amber-400 text-xs ml-auto mr-1">
          {t('message.fileMutationFailed', { count: failures.length })}
        </span>
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-amber-500 shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-amber-500 shrink-0" />
        )}
      </button>

      {expanded && (
        <div className="px-3 pb-2 space-y-1.5">
          {failures.map((f, i) => (
            <div
              key={`${f.path}-${i}`}
              className="flex flex-col gap-0.5 px-2 py-1.5 rounded bg-amber-100/60 dark:bg-amber-900/20 text-xs"
            >
              <span className="font-mono text-amber-900 dark:text-amber-100 break-all">{shortenPath(f.path)}</span>
              {f.error_preview && (
                <span className="text-amber-700/80 dark:text-amber-300/70 line-clamp-2">{f.error_preview}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
