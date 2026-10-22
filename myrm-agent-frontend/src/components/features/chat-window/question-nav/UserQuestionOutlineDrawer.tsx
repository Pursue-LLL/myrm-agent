/**
 * [INPUT]
 * - onJumpToMessageIndex: (index: number, messageId: string) => void
 * - onClose?: () => void
 *
 * [OUTPUT]
 * - UserQuestionOutlineDrawer: Drawer / popover outlining all user prompts in the session with direct anchors
 *
 * [POS]
 * Question outline drawer component for fast navigation (Item 43 P0).
 * Strictly under 200 lines. Zero `any`.
 */

'use client';

import React from 'react';
import { ListOrdered, X, ArrowRight, MessageSquare } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useUserQuestionNavStore } from './useUserQuestionNavStore';

interface UserQuestionOutlineDrawerProps {
  onJumpToMessageIndex: (index: number, messageId: string) => void;
  onClose?: () => void;
}

export const UserQuestionOutlineDrawer: React.FC<UserQuestionOutlineDrawerProps> = ({
  onJumpToMessageIndex,
  onClose,
}) => {
  const t = useTranslations('questionNav');
  const {
    questions,
    currentIndex,
    isOutlineOpen,
    setOutlineOpen,
    setCurrentIndex,
  } = useUserQuestionNavStore();

  if (!isOutlineOpen) {
    return null;
  }

  const handleClose = () => {
    setOutlineOpen(false);
    if (onClose) {
      onClose();
    }
  };

  const handleSelectQuestion = (index: number, messageId: string) => {
    setCurrentIndex(index);
    onJumpToMessageIndex(questions[index].messageIndex, messageId);
    setOutlineOpen(false);
    if (onClose) {
      onClose();
    }
  };

  return (
    <dialog
      open
      aria-labelledby="question-outline-title"
      className="fixed inset-0 z-50 flex h-full w-full items-center justify-end bg-black/40 backdrop-blur-xs p-0 m-0"
    >
      <div className="flex h-full w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900">
        {/* Header */}
        <header className="flex h-14 items-center justify-between border-b border-slate-200 px-5 dark:border-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600 dark:bg-blue-950/60 dark:text-blue-400">
              <ListOrdered className="h-4 w-4" />
            </div>
            <div>
              <h2
                id="question-outline-title"
                className="text-sm font-semibold text-slate-900 dark:text-slate-100"
              >
                {t('outlineDrawerTitle')}
              </h2>
              <span className="text-[11px] text-slate-500 dark:text-slate-400">
                {t('outlineDrawerSubtitle', { count: questions.length })}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={handleClose}
            aria-label={t('closeDrawer')}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        {/* Outline Question List */}
        <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-2">
          {questions.length === 0 ? (
            <div className="flex h-40 flex-col items-center justify-center text-xs text-slate-400">
              <MessageSquare className="h-8 w-8 stroke-1 text-slate-300 dark:text-slate-600 mb-2" />
              <span>{t('noQuestionsYet')}</span>
            </div>
          ) : (
            questions.map((q, idx) => {
              const isCurrent = idx === currentIndex;
              return (
                <button
                  key={q.messageId}
                  type="button"
                  onClick={() => handleSelectQuestion(idx, q.messageId)}
                  className={`group flex items-start gap-3 rounded-xl border p-3 text-left transition-all ${
                    isCurrent
                      ? 'border-blue-500 bg-blue-50/60 shadow-xs dark:border-blue-500 dark:bg-blue-950/40'
                      : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/60 dark:border-slate-800 dark:bg-slate-950 dark:hover:border-slate-700'
                  }`}
                >
                  <div
                    className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-xs font-bold ${
                      isCurrent
                        ? 'bg-blue-600 text-white'
                        : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
                    }`}
                  >
                    {q.questionNumber}
                  </div>
                  <div className="flex flex-col flex-1 min-w-0">
                    <p
                      className={`text-xs font-medium leading-relaxed line-clamp-2 ${
                        isCurrent
                          ? 'text-blue-950 dark:text-blue-100'
                          : 'text-slate-800 dark:text-slate-200'
                      }`}
                    >
                      {q.summary}
                    </p>
                    <div className="flex items-center gap-2 mt-1 text-[10px] text-slate-400">
                      <span>
                        {t('roundLabel', { num: q.questionNumber })}
                      </span>
                    </div>
                  </div>
                  <ArrowRight
                    className={`h-4 w-4 shrink-0 transition-transform group-hover:translate-x-0.5 ${
                      isCurrent
                        ? 'text-blue-600 dark:text-blue-400'
                        : 'text-slate-300 dark:text-slate-700'
                    }`}
                  />
                </button>
              );
            })
          )}
        </div>
      </div>
    </dialog>
  );
};

export default UserQuestionOutlineDrawer;
