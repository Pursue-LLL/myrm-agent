/**
 * [INPUT]
 * - ./ClarificationChrome::CheckCircleIcon / SkipIcon (POS: answered-state icons shared with the clarification card)
 * - @/store/chat/hitlAnswerRecord::AnswerLine (POS: one question and the answer given to it)
 *
 * [OUTPUT]
 * - HitlAnsweredNote: the banner a clarification card collapses into once it is settled
 *
 * [POS]
 * Presentation only: the caller decides the tone and the wording from the card's answer record, so the banner holds
 * no translations and no store access.
 */

import React from 'react';
import { cn } from '@/lib/utils';
import type { AnswerLine } from '@/store/chat/hitlAnswerRecord';

import { CheckCircleIcon, SkipIcon } from './ClarificationChrome';

interface HitlAnsweredNoteProps {
  /** `done` is an answer the agent acted on; `muted` is a skip, a denial, a timeout or a card someone else already handled. */
  tone: 'done' | 'muted';
  headline: string;
  lines?: readonly AnswerLine[];
}

const TONE_CLASSES = {
  done: {
    shell: 'border-emerald-500/30 bg-emerald-500/5',
    icon: 'text-emerald-500 dark:text-emerald-400',
    headline: 'text-emerald-700 dark:text-emerald-300',
  },
  muted: {
    shell: 'border-border/60 bg-muted/40',
    icon: 'text-muted-foreground',
    headline: 'text-muted-foreground',
  },
} as const;

const HitlAnsweredNote = ({ tone, headline, lines }: HitlAnsweredNoteProps) => {
  const classes = TONE_CLASSES[tone];
  const Icon = tone === 'done' ? CheckCircleIcon : SkipIcon;

  return (
    <div className={cn('mt-3 rounded-2xl border px-3 py-2.5 text-sm sm:mt-4 sm:px-4 sm:py-3', classes.shell)}>
      {/* The icon stays on the first line: a headline that wraps on a narrow screen must not float it to the middle. */}
      <div className="flex items-start gap-2.5">
        <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', classes.icon)} />
        <span className={cn('font-medium', classes.headline)}>{headline}</span>
      </div>
      {lines && lines.length > 0 ? (
        <ul className="mt-2 flex flex-col gap-1.5 border-t border-border/40 pt-2 pl-[1.625rem]">
          {lines.map((line) => (
            <li key={line.key} className="flex min-w-0 flex-col">
              {line.prompt ? <span className="text-xs text-muted-foreground">{line.prompt}</span> : null}
              <span className="whitespace-pre-wrap break-words text-foreground">{line.text}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
};

export default React.memo(HitlAnsweredNote);
