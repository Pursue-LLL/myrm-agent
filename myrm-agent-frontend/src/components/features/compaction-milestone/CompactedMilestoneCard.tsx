'use client';

/**
 * [INPUT]
 * - CompactionEntry from ./compactionTypes
 * - ReadOnlyTimeMachineDrawer from ./ReadOnlyTimeMachineDrawer
 * - useTranslations from next-intl (namespace: 'compaction')
 *
 * [OUTPUT]
 * - CompactedMilestoneCard: 5-section structured summary capsule card with token savings & time machine
 *
 * [POS]
 * Context compaction milestone visualizer in chat stream (Item 27).
 * Single file < 280 lines. Zero `any` types. Zero native emoji.
 */

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Sparkles,
  ChevronDown,
  ChevronUp,
  Target,
  CheckCircle2,
  FileCode2,
  Flame,
  ArrowRightCircle,
  FileText,
  Coins,
  History,
} from 'lucide-react';
import type { CompactionEntry } from './compactionTypes';
import { ReadOnlyTimeMachineDrawer } from './ReadOnlyTimeMachineDrawer';

interface CompactedMilestoneCardProps {
  entry: CompactionEntry;
  className?: string;
  defaultExpanded?: boolean;
}

export function CompactedMilestoneCard({
  entry,
  className = '',
  defaultExpanded = false,
}: CompactedMilestoneCardProps) {
  const t = useTranslations('compaction');
  const [isExpanded, setIsExpanded] = useState<boolean>(defaultExpanded);
  const [isTimeMachineOpen, setIsTimeMachineOpen] = useState<boolean>(false);

  const formattedTokens = entry.savedTokens.toLocaleString();
  // The archive loads lazily, so the count is 0 until the Time Machine has been opened.
  const hasMessageCount = entry.compactedMessagesCount > 0;

  return (
    <article
      aria-label={t('capsuleTitle')}
      className={`my-3 mx-auto w-full max-w-3xl rounded-2xl border border-primary/30 bg-card/80 shadow-xs backdrop-blur-md overflow-hidden select-none transition-all ${className}`}
    >
      {/* Header Capsule Bar */}
      <button
        type="button"
        aria-expanded={isExpanded}
        aria-label={isExpanded ? t('collapseSummary') : t('expandSummary')}
        onClick={() => setIsExpanded((prev) => !prev)}
        className="w-full p-3 flex items-center justify-between gap-3 bg-primary/5 hover:bg-primary/10 transition-colors cursor-pointer text-left border-0"
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-8 h-8 rounded-xl bg-primary/15 text-primary flex items-center justify-center shrink-0 shadow-2xs">
            <Sparkles className="w-4 h-4" />
          </div>

          <div className="flex flex-col min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-xs text-foreground truncate">
                {t('capsuleTitle')}
              </span>
              {hasMessageCount && (
                <span className="text-[10px] font-mono px-2 py-0.2 rounded-full bg-primary/10 text-primary font-medium">
                  {entry.compactedMessagesCount} msgs
                </span>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground truncate font-mono">
              {hasMessageCount
                ? t('capsuleSubtitle', { count: entry.compactedMessagesCount, tokens: formattedTokens })
                : t('capsuleSubtitleTokensOnly', { tokens: formattedTokens })}
            </p>
          </div>
        </div>

        {/* Right Badge: Saved Tokens + Expand Toggle Indicator */}
        <div className="flex items-center gap-2 shrink-0">
          <span className="hidden sm:flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-semibold">
            <Coins className="w-3 h-3" />
            <span>+{formattedTokens} tokens</span>
          </span>

          <span className="p-1 rounded-lg text-muted-foreground transition-colors">
            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </span>
        </div>
      </button>

      {/* Expanded 5-Section Summary Canvas */}
      {isExpanded && (
        <div className="p-3.5 border-t border-border/50 text-xs flex flex-col gap-3 select-text bg-background/50">
          {/* Section 1: Goal */}
          {entry.goal && (
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-1.5 font-semibold text-foreground text-[11px]">
                <Target className="w-3.5 h-3.5 text-blue-500" />
                <span>{t('goalTitle')}</span>
              </div>
              <p className="text-muted-foreground leading-relaxed pl-5 text-[11px]">
                {entry.goal}
              </p>
            </div>
          )}

          {/* Section 2: Progress */}
          {entry.progress && (
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-1.5 font-semibold text-foreground text-[11px]">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                <span>{t('progressTitle')}</span>
              </div>
              <p className="text-muted-foreground leading-relaxed pl-5 text-[11px]">
                {entry.progress}
              </p>
            </div>
          )}

          {/* Section 3: Key Decisions & ADR */}
          {entry.keyDecisions && entry.keyDecisions.length > 0 && (
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-1.5 font-semibold text-foreground text-[11px]">
                <FileCode2 className="w-3.5 h-3.5 text-purple-500" />
                <span>{t('keyDecisionsTitle')}</span>
              </div>
              <ul className="list-disc list-inside text-muted-foreground leading-relaxed pl-2 text-[11px] space-y-0.5">
                {entry.keyDecisions.map((dec, i) => (
                  <li key={`decision-${i}`}>{dec}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Section 4: Next Steps */}
          {entry.nextSteps && entry.nextSteps.length > 0 && (
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-1.5 font-semibold text-foreground text-[11px]">
                <ArrowRightCircle className="w-3.5 h-3.5 text-amber-500" />
                <span>{t('nextStepsTitle')}</span>
              </div>
              <ul className="list-disc list-inside text-muted-foreground leading-relaxed pl-2 text-[11px] space-y-0.5">
                {entry.nextSteps.map((step, i) => (
                  <li key={`next-step-${i}`}>{step}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Section 5: Critical Context */}
          {entry.criticalContext && (
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-1.5 font-semibold text-rose-600 dark:text-rose-400 text-[11px]">
                <Flame className="w-3.5 h-3.5" />
                <span>{t('criticalContextTitle')}</span>
              </div>
              <p className="text-muted-foreground leading-relaxed pl-5 text-[11px]">
                {entry.criticalContext}
              </p>
            </div>
          )}

          {/* Touched Files Badges */}
          {entry.filesTouched && entry.filesTouched.length > 0 && (
            <div className="pt-2 border-t border-border/40 flex flex-wrap items-center gap-1.5">
              <span className="flex items-center gap-1 text-[10px] text-muted-foreground font-semibold uppercase tracking-wider mr-1">
                <FileText className="w-3 h-3" />
                <span>{t('filesTouchedTitle')}:</span>
              </span>
              {entry.filesTouched.map((f, i) => (
                <span
                  key={`file-${i}`}
                  className="font-mono text-[10px] px-2 py-0.5 rounded-md bg-muted text-foreground/80 border border-border/50 truncate max-w-[200px]"
                >
                  {f}
                </span>
              ))}
            </div>
          )}

          {/* Time Machine Entrance Toggle */}
          <div className="pt-2 border-t border-border/40 flex items-center justify-between">
            <button
              type="button"
              onClick={() => setIsTimeMachineOpen((prev) => !prev)}
              className="flex items-center gap-1.5 text-[11px] font-medium text-primary hover:text-primary/80 transition-colors p-1 rounded-md"
            >
              <History className="w-3.5 h-3.5" />
              <span>
                {isTimeMachineOpen
                  ? t('timeMachine.closeButton')
                  : t('timeMachine.openButton', { count: entry.originalMessages.length })}
              </span>
            </button>
          </div>

          {/* Inline Time Machine Drawer */}
          {isTimeMachineOpen && (
            <ReadOnlyTimeMachineDrawer
              messages={entry.originalMessages}
              onClose={() => setIsTimeMachineOpen(false)}
            />
          )}
        </div>
      )}
    </article>
  );
}
