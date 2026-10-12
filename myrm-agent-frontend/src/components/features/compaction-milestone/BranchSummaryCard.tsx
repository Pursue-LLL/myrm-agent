'use client';

/**
 * [INPUT]
 * - BranchSummaryEntry from ./compactionTypes
 * - useTranslations from next-intl (namespace: 'compaction.branchSummary')
 *
 * [OUTPUT]
 * - BranchSummaryCard: Cross-branch experience fly-line card with warp-back action
 *
 * [POS]
 * Branch exploration context visualizer in chat stream (Item 27).
 * Single file < 160 lines. Zero `any` types. Zero native emoji.
 */

import React from 'react';
import { useTranslations } from 'next-intl';
import { GitBranch, GitFork, ArrowUpRight, Lightbulb } from 'lucide-react';
import type { BranchSummaryEntry } from './compactionTypes';

interface BranchSummaryCardProps {
  entry: BranchSummaryEntry;
  className?: string;
  onWarpToSource?: (branchId: string) => void;
}

export function BranchSummaryCard({
  entry,
  className = '',
  onWarpToSource,
}: BranchSummaryCardProps) {
  const t = useTranslations('compaction.branchSummary');

  const handleWarp = () => {
    if (onWarpToSource) {
      onWarpToSource(entry.sourceBranchId);
    } else {
      window.dispatchEvent(
        new CustomEvent('myrm:warp-to-branch', {
          detail: { branchId: entry.sourceBranchId },
        }),
      );
    }
  };

  return (
    <article
      aria-label="Cross-Branch Experience Card"
      className={`my-3 mx-auto w-full max-w-3xl rounded-2xl border border-indigo-500/30 bg-card/80 p-3.5 shadow-xs backdrop-blur-md flex flex-col gap-2.5 select-none transition-all ${className}`}
    >
      {/* Top Fly-line Badge & Branch Title */}
      <div className="flex items-center justify-between gap-2 border-b border-border/50 pb-2 text-xs">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-6 h-6 rounded-lg bg-indigo-500/15 text-indigo-500 flex items-center justify-center shrink-0">
            <GitBranch className="w-3.5 h-3.5" />
          </div>
          <span className="font-semibold text-foreground truncate">
            {t('inheritedBadge')}
          </span>
          <span className="text-[11px] font-mono text-muted-foreground truncate">
            {t('sourceBranchLabel')}: <strong className="text-foreground">{entry.sourceBranchName}</strong>
          </span>
        </div>

        {/* Warp button */}
        <button
          type="button"
          onClick={handleWarp}
          className="flex items-center gap-1 text-[11px] font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 bg-indigo-500/10 hover:bg-indigo-500/15 px-2.5 py-1 rounded-lg transition-colors shrink-0"
        >
          <span>{t('warpToSource')}</span>
          <ArrowUpRight className="w-3 h-3" />
        </button>
      </div>

      {/* Summary Narrative */}
      <div className="text-xs text-foreground/85 leading-relaxed select-text font-sans">
        {entry.summary}
      </div>

      {/* Key Takeaways */}
      {entry.keyTakeaways && entry.keyTakeaways.length > 0 && (
        <div className="p-2.5 rounded-xl bg-muted/40 border border-border/40 flex flex-col gap-1.5 select-text">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold text-indigo-600 dark:text-indigo-400">
            <Lightbulb className="w-3.5 h-3.5" />
            <span>{t('keyTakeawaysTitle')}</span>
          </div>
          <ul className="list-disc list-inside text-muted-foreground text-[11px] space-y-0.5 leading-relaxed pl-1">
            {entry.keyTakeaways.map((item, idx) => (
              <li key={`takeaway-${idx}`}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Fork metadata footer */}
      {entry.forkedAtMessageId && (
        <div className="flex items-center gap-1 text-[10px] font-mono text-muted-foreground/70 pt-1">
          <GitFork className="w-3 h-3 text-muted-foreground/60" />
          <span>
            {t('forkIndicator')}: {entry.forkedAtMessageId}
          </span>
        </div>
      )}
    </article>
  );
}
