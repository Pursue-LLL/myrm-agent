'use client';

import { useRef } from 'react';
import type { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { CheckCircleIcon, XCircleIcon } from './goal-icons';
import type { GoalState } from './goalStatusTypes';
import { cn } from '@/lib/utils/classnameUtils';
import { REVEAL_ON_HOVER } from '@/lib/utils/a11y';

interface GoalSubgoalsSectionProps {
  goal: GoalState;
  isTerminal: boolean;
  /** Resolves whether the server took the sub-goal. */
  onAddSubgoal: (text: string) => Promise<boolean>;
  onRemoveSubgoal: (index: number) => void;
  t: ReturnType<typeof useTranslations>;
}

export function GoalSubgoalsSection({ goal, isTerminal, onAddSubgoal, onRemoveSubgoal, t }: GoalSubgoalsSectionProps) {
  const adding = useRef(false);

  // The text leaves the box only once the server took it, so a refused sub-goal stays there to be edited.
  // One add at a time: a second submit while the request is out would add the same text twice.
  const addFrom = async (input: HTMLInputElement | null) => {
    if (!input || adding.current) {
      return;
    }
    if (!input.value.trim()) {
      input.value = '';
      return;
    }
    adding.current = true;
    const sent = input.value;
    try {
      // Text typed while the request was out is not the one that was taken, so it stays.
      if ((await onAddSubgoal(sent)) && input.value === sent) {
        input.value = '';
      }
    } finally {
      adding.current = false;
    }
  };

  return (
    <div className="mt-4 border-t border-border/50 pt-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-foreground">{t('subgoals') || 'Subgoals'}</span>
      </div>
      {goal.subgoals && goal.subgoals.length > 0 && (
        <ul className="space-y-1.5 mb-3">
          {goal.subgoals.map((sg, idx) => (
            <li
              key={idx}
              className="flex items-start gap-2 text-xs bg-background/50 p-2 rounded-lg border border-border/50 group"
            >
              <div className="flex-shrink-0 mt-0.5">
                <CheckCircleIcon className="h-3.5 w-3.5 text-muted-foreground" />
              </div>
              <span className="flex-1 text-muted-foreground break-words leading-relaxed">{sg.text}</span>
              {!isTerminal && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onRemoveSubgoal(idx);
                  }}
                  className={cn('text-muted-foreground hover:text-destructive transition-opacity', REVEAL_ON_HOVER)}
                  aria-label="Remove subgoal"
                >
                  <XCircleIcon className="h-3.5 w-3.5" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {!isTerminal && (
        <div className="flex gap-2">
          <Input
            placeholder={t('subgoalPlaceholder') || 'Add acceptance criteria or sub-task...'}
            className="h-8 text-xs bg-background/50 border-border/50"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                void addFrom(e.currentTarget);
              }
            }}
          />
          <Button
            size="sm"
            variant="secondary"
            className="h-8 px-3 shrink-0 text-xs"
            onClick={(e) => {
              e.stopPropagation();
              void addFrom(e.currentTarget.previousElementSibling as HTMLInputElement | null);
            }}
          >
            {t('addSubgoal') || 'Add'}
          </Button>
        </div>
      )}
    </div>
  );
}
