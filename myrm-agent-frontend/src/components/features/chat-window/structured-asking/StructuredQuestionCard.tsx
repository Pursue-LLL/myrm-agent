/**
 * [INPUT]
 * - structuredAskingTypes: StructuredQuestionCardProps, QuestionOption, StructuredQuestionResponse
 * - useStructuredAskingStore: useStructuredAskingStore
 *
 * [OUTPUT]
 * - StructuredQuestionCard: Interactive card for structured questions with keyboard shortcuts & skip control
 *
 * [POS]
 * Structured Asking decision card component (Item 47 P0).
 * Strictly under 320 lines. Zero `any`.
 */

'use client';

import React, { memo, useCallback, useEffect, useMemo } from 'react';
import {
  HelpCircle,
  CheckCircle,
  SkipForward,
  Sparkles,
  CornerDownLeft,
  Check,
  CheckSquare,
  Square,
  Circle,
  CheckCircle2,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useStructuredAskingStore } from './useStructuredAskingStore';
import type { StructuredQuestionCardProps } from './structuredAskingTypes';

export const StructuredQuestionCard: React.FC<StructuredQuestionCardProps> = memo(({
  payload,
  onSubmitResponse,
  onSkip,
  className = '',
  enableKeyboardShortcuts = true,
}) => {
  const t = useTranslations('structuredAsking');
  const { questionId, question, context, options, questionType, allowSkip = true, status, response, defaultOptionId } = payload;

  const {
    getDraft,
    selectOption,
    setTextInput,
    buildResponse,
  } = useStructuredAskingStore();

  const draft = getDraft(questionId);
  const isPending = status === 'pending';

  const isOptionSelected = useCallback((optionId: string) => {
    return draft.selectedOptionIds.includes(optionId);
  }, [draft.selectedOptionIds]);

  const handleSelect = useCallback((optionId: string) => {
    if (!isPending) {
      return;
    }
    selectOption(questionId, optionId, questionType);
  }, [isPending, questionId, questionType, selectOption]);

  const handleSubmit = useCallback(() => {
    if (!isPending) {
      return;
    }
    const res = buildResponse(questionId, false);
    if (onSubmitResponse) {
      onSubmitResponse(res);
    }
  }, [isPending, buildResponse, questionId, onSubmitResponse]);

  const handleSkip = useCallback(() => {
    if (!isPending) {
      return;
    }
    const res = buildResponse(questionId, true, defaultOptionId);
    if (onSkip) {
      onSkip();
    } else if (onSubmitResponse) {
      onSubmitResponse(res);
    }
  }, [isPending, buildResponse, questionId, defaultOptionId, onSkip, onSubmitResponse]);

  // Keyboard shortcut listener for numbers (1~9), Enter, and Escape
  useEffect(() => {
    if (!enableKeyboardShortcuts || !isPending) {
      return;
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore if user is typing in an input or textarea
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) {
        return;
      }

      // Numbers 1-9 for quick selection
      const keyNum = parseInt(e.key, 10);
      if (!isNaN(keyNum) && keyNum >= 1 && keyNum <= options.length) {
        e.preventDefault();
        const targetOption = options[keyNum - 1];
        if (targetOption) {
          selectOption(questionId, targetOption.id, questionType);
        }
        return;
      }

      // Enter to submit
      if (e.key === 'Enter') {
        if (draft.selectedOptionIds.length > 0 || questionType === 'text_slot') {
          e.preventDefault();
          handleSubmit();
        }
        return;
      }

      // Escape to skip
      if (e.key === 'Escape' && allowSkip) {
        e.preventDefault();
        handleSkip();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [
    enableKeyboardShortcuts,
    isPending,
    options,
    questionId,
    questionType,
    selectOption,
    draft.selectedOptionIds.length,
    allowSkip,
    handleSubmit,
    handleSkip,
  ]);

  const canSubmit = useMemo(() => {
    if (!isPending) {
      return false;
    }
    if (questionType === 'text_slot') {
      return draft.textInput.trim().length > 0;
    }
    return draft.selectedOptionIds.length > 0;
  }, [isPending, questionType, draft.textInput, draft.selectedOptionIds.length]);

  return (
    <div
      data-testid="structured-question-card"
      className={`rounded-2xl border p-4.5 sm:p-5 transition-all shadow-xs ${
        isPending
          ? 'bg-white dark:bg-slate-900 border-blue-200 dark:border-blue-900/60 ring-1 ring-blue-500/10'
          : 'bg-slate-50/70 dark:bg-slate-900/40 border-slate-200 dark:border-slate-800'
      } ${className}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-start gap-2.5 min-w-0">
          <span
            className={`p-1.5 rounded-lg shrink-0 ${
              isPending
                ? 'bg-blue-50 dark:bg-blue-950/80 text-blue-600 dark:text-blue-400'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-500'
            }`}
          >
            {isPending ? <HelpCircle className="w-4 h-4" /> : <CheckCircle className="w-4 h-4" />}
          </span>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 leading-snug">
              {question}
            </h3>
            {context && (
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                {context}
              </p>
            )}
          </div>
        </div>

        {/* Status Badge */}
        {!isPending && (
          <span
            data-testid="status-badge"
            className={`inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium rounded-full shrink-0 ${
              status === 'skipped'
                ? 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300'
                : 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400'
            }`}
          >
            {status === 'skipped' ? (
              <>
                <SkipForward className="w-3 h-3" />
                <span>{t('skippedBadge')}</span>
              </>
            ) : (
              <>
                <Check className="w-3 h-3" />
                <span>{t('answeredBadge')}</span>
              </>
            )}
          </span>
        )}
      </div>

      {/* Options List */}
      {isPending ? (
        <div className="flex flex-col gap-2 mt-3.5" data-testid="options-container">
          {options.map((opt, idx) => {
            const selected = isOptionSelected(opt.id);
            const isMulti = questionType === 'multi_choice';
            const shortcutNum = idx + 1 <= 9 ? idx + 1 : null;

            return (
              <button
                key={opt.id}
                type="button"
                data-testid={`option-item-${opt.id}`}
                onClick={() => {
                  handleSelect(opt.id);
                }}
                className={`w-full text-left p-3 rounded-xl border transition-all flex items-start justify-between gap-3 ${
                  selected
                    ? 'border-blue-500 bg-blue-50/70 dark:bg-blue-950/40 text-blue-950 dark:text-blue-100 shadow-xs'
                    : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800/60 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-800 dark:text-slate-200'
                }`}
              >
                <div className="flex items-start gap-2.5 min-w-0">
                  <span className="mt-0.5 shrink-0 text-slate-400">
                    {isMulti ? (
                      selected ? (
                        <CheckSquare className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                      ) : (
                        <Square className="w-4 h-4" />
                      )
                    ) : selected ? (
                      <CheckCircle2 className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                    ) : (
                      <Circle className="w-4 h-4" />
                    )}
                  </span>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium leading-snug">
                        {opt.label}
                      </span>
                      {opt.isRecommended && (
                        <span className="inline-flex items-center gap-0.5 px-1.5 py-0.2 text-[10px] font-semibold text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/60 rounded">
                          <Sparkles className="w-2.5 h-2.5" />
                          <span>{t('recommended')}</span>
                        </span>
                      )}
                    </div>
                    {opt.description && (
                      <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400 leading-normal">
                        {opt.description}
                      </p>
                    )}
                  </div>
                </div>

                {shortcutNum && (
                  <span className="shrink-0 px-1.5 py-0.5 text-[10px] font-mono font-medium text-slate-400 bg-slate-100 dark:bg-slate-700/60 rounded border border-slate-200/80 dark:border-slate-700">
                    {shortcutNum}
                  </span>
                )}
              </button>
            );
          })}

          {/* Text slot input if applicable */}
          {questionType === 'text_slot' && (
            <div className="mt-2">
              <input
                type="text"
                data-testid="text-slot-input"
                value={draft.textInput}
                onChange={(e) => {
                  setTextInput(questionId, e.target.value);
                }}
                placeholder={t('textSlotPlaceholder')}
                className="w-full text-xs p-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          )}

          {/* Bottom Actions Toolbar */}
          <div className="flex items-center justify-between gap-3 mt-3 pt-2 border-t border-slate-100 dark:border-slate-800">
            {allowSkip ? (
              <button
                type="button"
                data-testid="skip-button"
                onClick={handleSkip}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 rounded-md transition-colors"
              >
                <SkipForward className="w-3.5 h-3.5" />
                <span>{t('skipControl')}</span>
              </button>
            ) : (
              <div />
            )}

            <button
              type="button"
              data-testid="submit-button"
              disabled={!canSubmit}
              onClick={handleSubmit}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium rounded-lg text-white bg-blue-600 hover:bg-blue-700 disabled:bg-slate-200 dark:disabled:bg-slate-800 disabled:text-slate-400 transition-colors shadow-xs"
            >
              <span>{t('confirmSelection')}</span>
              <CornerDownLeft className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      ) : (
        /* Answered / Skipped Summary View */
        <div className="mt-2 text-xs text-slate-600 dark:text-slate-300 space-y-1" data-testid="answered-summary">
          {response?.isSkipped ? (
            <p className="italic text-slate-400 dark:text-slate-500">
              {t('skippedExplanation')}
            </p>
          ) : (
            <div>
              <span className="font-medium text-slate-700 dark:text-slate-200">
                {t('userChoseLabel')}:
              </span>{' '}
              {options
                .filter((o) => response?.selectedOptionIds.includes(o.id))
                .map((o) => o.label)
                .join(', ') || response?.textValue || t('noneSelected')}
            </div>
          )}
        </div>
      )}
    </div>
  );
});

StructuredQuestionCard.displayName = 'StructuredQuestionCard';
