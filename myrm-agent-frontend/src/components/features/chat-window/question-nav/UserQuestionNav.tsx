/**
 * [INPUT]
 * - onJumpToMessageIndex: (index: number, messageId: string) => void
 * - className?: string
 * - visible?: boolean
 *
 * [OUTPUT]
 * - UserQuestionNav: Floating capsule toolbar for fast question jumping & outline toggling
 *
 * [POS]
 * Floating question anchor navigator for long chat sessions (Item 43 P0).
 * Strictly under 220 lines. Zero `any`.
 */

'use client';

import React from 'react';
import { ChevronUp, ChevronDown, ListOrdered } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import { useUserQuestionNavStore } from './useUserQuestionNavStore';
import type { UserQuestionAnchor } from './userQuestionNavTypes';

interface UserQuestionNavProps {
  onJumpToMessageIndex: (index: number, messageId: string) => void;
  className?: string;
  visible?: boolean;
}

export const UserQuestionNav: React.FC<UserQuestionNavProps> = ({
  onJumpToMessageIndex,
  className = '',
  visible = true,
}) => {
  const t = useTranslations('questionNav');
  const {
    questions,
    currentIndex,
    setCurrentIndex,
    setOutlineOpen,
    getPreviousQuestion,
    getNextQuestion,
  } = useUserQuestionNavStore();

  if (!visible || questions.length <= 1) {
    return null;
  }

  const prevQuestion: UserQuestionAnchor | null = getPreviousQuestion();
  const nextQuestion: UserQuestionAnchor | null = getNextQuestion();

  const handleJumpPrev = () => {
    if (prevQuestion) {
      setCurrentIndex(currentIndex - 1);
      onJumpToMessageIndex(prevQuestion.messageIndex, prevQuestion.messageId);
    }
  };

  const handleJumpNext = () => {
    if (nextQuestion) {
      setCurrentIndex(currentIndex + 1);
      onJumpToMessageIndex(nextQuestion.messageIndex, nextQuestion.messageId);
    }
  };

  return (
    <TooltipProvider delayDuration={150}>
      <aside
        aria-label="User Question Navigation HUD"
        className={`fixed right-4 md:right-6 bottom-56 md:bottom-60 z-40 flex flex-col items-center rounded-full border border-slate-200/80 bg-white/90 p-1 shadow-lg backdrop-blur-md dark:border-slate-800 dark:bg-slate-900/90 ${className}`}
      >
        {/* Previous Question Jump Button */}
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={handleJumpPrev}
              disabled={!prevQuestion}
              aria-label={t('prevQuestionAria')}
              className={`flex h-7 w-7 items-center justify-center rounded-full transition-colors ${
                prevQuestion
                  ? 'text-slate-700 hover:bg-slate-100 hover:text-blue-600 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-blue-400'
                  : 'cursor-not-allowed text-slate-300 dark:text-slate-700'
              }`}
            >
              <ChevronUp className="h-4 w-4" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="left" className="max-w-64 p-2 text-xs">
            <p className="font-semibold">{t('prevQuestionTitle')}</p>
            {prevQuestion ? (
              <p className="mt-0.5 text-slate-500 dark:text-slate-400 line-clamp-2">
                {prevQuestion.summary}
              </p>
            ) : (
              <p className="mt-0.5 text-slate-400 dark:text-slate-500">{t('alreadyAtFirst')}</p>
            )}
          </TooltipContent>
        </Tooltip>

        {/* Question Counter / Outline Drawer Toggle */}
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={() => setOutlineOpen(true)}
              aria-label={t('openOutlineAria')}
              className="my-0.5 flex h-7 items-center gap-1 rounded-full px-2 text-[11px] font-bold text-slate-700 hover:bg-blue-50 hover:text-blue-600 dark:text-slate-300 dark:hover:bg-blue-950/40 dark:hover:text-blue-400 transition-colors"
            >
              <ListOrdered className="h-3 w-3 shrink-0" />
              <span>
                {currentIndex + 1}/{questions.length}
              </span>
            </button>
          </TooltipTrigger>
          <TooltipContent side="left" className="p-2 text-xs">
            <p className="font-semibold">{t('openOutlineTooltip')}</p>
            <p className="text-[11px] text-slate-400">{t('openOutlineDesc')}</p>
          </TooltipContent>
        </Tooltip>

        {/* Next Question Jump Button */}
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={handleJumpNext}
              disabled={!nextQuestion}
              aria-label={t('nextQuestionAria')}
              className={`flex h-7 w-7 items-center justify-center rounded-full transition-colors ${
                nextQuestion
                  ? 'text-slate-700 hover:bg-slate-100 hover:text-blue-600 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-blue-400'
                  : 'cursor-not-allowed text-slate-300 dark:text-slate-700'
              }`}
            >
              <ChevronDown className="h-4 w-4" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="left" className="max-w-64 p-2 text-xs">
            <p className="font-semibold">{t('nextQuestionTitle')}</p>
            {nextQuestion ? (
              <p className="mt-0.5 text-slate-500 dark:text-slate-400 line-clamp-2">
                {nextQuestion.summary}
              </p>
            ) : (
              <p className="mt-0.5 text-slate-400 dark:text-slate-500">{t('alreadyAtLast')}</p>
            )}
          </TooltipContent>
        </Tooltip>
      </aside>
    </TooltipProvider>
  );
};

export default UserQuestionNav;
