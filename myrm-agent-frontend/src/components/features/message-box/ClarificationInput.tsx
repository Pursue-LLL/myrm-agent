'use client';

/**
 * [INPUT]
 * @/store/chat/types::ClarificationForm (POS: structured clarification form schema)
 * @/services/chat::submitClarifyResponse (POS: clarification answer submission API)
 * @/store/useChatStore::sendMessage (POS: resume-mode clarification send path)
 *
 * [OUTPUT]
 * ClarificationInput: Renders single-question and structured clarification forms.
 *
 * [POS]
 * Chat clarification answer surface. Bridges assistant clarification messages to
 * user input and the appropriate submission path.
 */

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { submitClarifyResponse } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import type { ClarificationForm } from '@/store/chat/types';
import { cn } from '@/lib/utils';

const SendIcon = ({ className }: { className?: string }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M22 2 11 13" />
    <path d="M22 2 15 22 11 13 2 9z" />
  </svg>
);

const SkipIcon = ({ className }: { className?: string }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <polygon points="5 4 15 12 5 20 5 4" />
    <line x1="19" y1="5" x2="19" y2="19" />
  </svg>
);

const CheckCircleIcon = ({ className }: { className?: string }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
    <polyline points="22 4 12 14.01 9 11.01" />
  </svg>
);

const CheckMarkIcon = () => (
  <svg
    width="10"
    height="10"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="3"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

interface OptionPillProps {
  label: string;
  description?: string;
  selected: boolean;
  allowMultiple: boolean;
  disabled: boolean;
  onSelect: () => void;
}

const OptionPill = ({ label, description, selected, allowMultiple, disabled, onSelect }: OptionPillProps) => (
  <button
    type="button"
    onClick={onSelect}
    disabled={disabled}
    className={cn(
      'group max-w-full rounded-full border px-3 py-2 text-left text-sm transition-all duration-200 sm:px-4 sm:py-2.5',
      selected
        ? 'border-primary/70 bg-primary/10 text-primary ring-2 ring-primary/20'
        : 'border-border/70 bg-background/80 text-foreground hover:border-primary/40 hover:bg-primary/5',
    )}
  >
    <div className="flex items-start gap-2.5">
      <div
        className={cn(
          'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center border transition-colors',
          allowMultiple ? 'rounded' : 'rounded-full',
          selected ? 'border-primary bg-primary text-primary-foreground' : 'border-input bg-background',
        )}
      >
        {selected ? <CheckMarkIcon /> : null}
      </div>
      <div className="min-w-0 flex flex-col gap-0.5">
        <span className={cn('font-medium leading-snug', selected && 'text-primary')}>{label}</span>
        {description ? <span className="text-xs leading-relaxed text-muted-foreground">{description}</span> : null}
      </div>
    </div>
  </button>
);

const clarificationTextareaClass =
  'w-full resize-none rounded-xl border border-border/70 bg-background/90 px-3 py-2.5 text-sm leading-relaxed placeholder:text-muted-foreground transition-colors focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/25 sm:px-4 sm:py-3';

interface ClarificationInputProps {
  messageId: string;
  answered: boolean;
  options?: string[];
  allowMultiple?: boolean;
  title?: string;
  form?: ClarificationForm;
  isResumeMode?: boolean;
}

const ClarificationInput = ({
  messageId,
  answered,
  options,
  allowMultiple,
  title,
  form,
  isResumeMode,
}: ClarificationInputProps) => {
  const t = useTranslations('chat.clarification');
  const [input, setInput] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [selectedOptions, setSelectedOptions] = useState<string[]>([]);
  const [formTexts, setFormTexts] = useState<Record<string, string>>({});
  const [formSelections, setFormSelections] = useState<Record<string, string[]>>({});
  const hasStructuredForm = Boolean(form && form.questions.length > 0);
  const sendMessage = useChatStore((state) => state.sendMessage);

  const markAnswered = () => {
    useChatStore.setState((state) => {
      const idx = state.messages.findIndex((m) => m.messageId === messageId);
      if (idx !== -1 && state.messages[idx].clarification) {
        state.messages[idx].clarification!.answered = true;
      }
    });
  };

  const toggleOption = (opt: string) => {
    if (allowMultiple) {
      setSelectedOptions((prev) => (prev.includes(opt) ? prev.filter((item) => item !== opt) : [...prev, opt]));
      return;
    }
    setSelectedOptions([opt]);
  };

  const toggleFormOption = (questionId: string, optionLabel: string, questionAllowMultiple: boolean) => {
    setFormSelections((prev) => {
      const current = prev[questionId] ?? [];
      const next = questionAllowMultiple
        ? current.includes(optionLabel)
          ? current.filter((item) => item !== optionLabel)
          : [...current, optionLabel]
        : [optionLabel];
      return { ...prev, [questionId]: next };
    });
  };

  const buildSingleAnswer = (): string | string[] | null => {
    const trimmedInput = input.trim();
    const answers = [...selectedOptions];
    if (trimmedInput) {
      answers.push(trimmedInput);
    }
    if (answers.length === 0) {
      return null;
    }
    return answers.length === 1 ? answers[0] : answers;
  };

  const buildStructuredAnswer = (): Record<string, string | string[]> | null => {
    const answers: Record<string, string | string[]> = {};

    for (const question of form?.questions ?? []) {
      const selected = formSelections[question.id] ?? [];
      const text = (formTexts[question.id] ?? '').trim();
      const parts = [...selected];
      if (text) {
        parts.push(text);
      }

      if (parts.length === 0) {
        continue;
      }
      answers[question.id] = parts.length === 1 ? parts[0] : parts;
    }

    return Object.keys(answers).length > 0 ? answers : null;
  };

  const handleSubmit = async () => {
    if (submitting) return;

    const finalAnswer = hasStructuredForm ? buildStructuredAnswer() : buildSingleAnswer();
    if (!finalAnswer) return;

    setSubmitting(true);
    try {
      if (isResumeMode) {
        await sendMessage('', messageId, undefined, finalAnswer);
      } else {
        await submitClarifyResponse(messageId, finalAnswer);
      }
      markAnswered();
    } catch (err) {
      console.error('Failed to submit clarification:', err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSkip = async () => {
    if (submitting) return;
    setSubmitting(true);
    try {
      if (isResumeMode) {
        await sendMessage('', messageId, undefined, null);
      } else {
        await submitClarifyResponse(messageId, '');
      }
      markAnswered();
    } catch (err) {
      console.error('Failed to skip clarification:', err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing) return;
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  if (answered) {
    return (
      <div className="mt-3 flex items-center gap-2.5 rounded-2xl border border-emerald-500/30 bg-emerald-500/5 px-3 py-2.5 text-sm sm:mt-4 sm:px-4 sm:py-3">
        <CheckCircleIcon className="h-4 w-4 shrink-0 text-emerald-500 dark:text-emerald-400" />
        <span className="font-medium text-emerald-700 dark:text-emerald-300">{t('answered')}</span>
      </div>
    );
  }

  const hasStructuredAnswer = hasStructuredForm
    ? (form?.questions ?? []).some((question) => {
        const selected = formSelections[question.id] ?? [];
        const text = (formTexts[question.id] ?? '').trim();
        return selected.length > 0 || text.length > 0;
      })
    : false;

  const isSubmitDisabled =
    submitting || (hasStructuredForm ? !hasStructuredAnswer : selectedOptions.length === 0 && !input.trim());

  const displayTitle = title ?? form?.title ?? t('formTitle');
  const questionCount = form?.questions.length ?? 0;

  const renderActions = () => (
    <div className="flex flex-col-reverse gap-2 border-t border-border/50 pt-3 sm:flex-row sm:justify-end sm:pt-4">
      <button
        type="button"
        onClick={handleSkip}
        disabled={submitting}
        className="inline-flex w-full items-center justify-center gap-1.5 rounded-full border border-border/70 bg-background/80 px-4 py-2.5 text-sm text-muted-foreground transition-colors hover:border-border hover:bg-accent/60 disabled:opacity-50 sm:w-auto sm:py-2"
      >
        <SkipIcon className="h-3.5 w-3.5" />
        {t('skip')}
      </button>
      <button
        type="button"
        onClick={handleSubmit}
        disabled={isSubmitDisabled}
        className="inline-flex w-full items-center justify-center gap-1.5 rounded-full bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50 sm:w-auto sm:py-2"
      >
        <SendIcon className="h-3.5 w-3.5" />
        {t('submit')}
      </button>
    </div>
  );

  return (
    <div className="mt-3 sm:mt-4">
      <div className="relative overflow-hidden rounded-2xl border border-border/60 bg-card/90 backdrop-blur-xl">
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-primary/8 via-transparent to-violet-500/5 dark:from-primary/12 dark:to-violet-500/8" />

        <div className="relative flex flex-col gap-4 p-3 sm:gap-5 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex min-w-0 flex-col gap-1">
              <span className="text-sm font-semibold leading-snug text-foreground sm:text-base">{displayTitle}</span>
              {hasStructuredForm && questionCount > 1 ? (
                <span className="text-xs text-muted-foreground">{t('questionCount', { count: questionCount })}</span>
              ) : null}
            </div>
            <span className="shrink-0 rounded-full border border-primary/25 bg-primary/10 px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide text-primary">
              {t('badge')}
            </span>
          </div>

          {hasStructuredForm ? (
            <div className="flex flex-col gap-3 sm:gap-4">
              {(form?.questions ?? []).map((question, index) => {
                const selected = formSelections[question.id] ?? [];
                const questionText = formTexts[question.id] ?? '';
                const questionAllowMultiple = question.allowMultiple ?? false;
                return (
                  <div
                    key={question.id}
                    className="flex flex-col gap-3 rounded-xl border border-border/60 bg-background/70 p-3 sm:gap-4 sm:p-4"
                  >
                    <div className="flex items-start gap-2.5">
                      {questionCount > 1 ? (
                        <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/15 text-[11px] font-semibold text-primary">
                          {index + 1}
                        </span>
                      ) : null}
                      <p className="text-sm font-medium leading-relaxed text-foreground sm:text-[15px]">{question.prompt}</p>
                    </div>

                    {question.options && question.options.length > 0 ? (
                      <div className="flex flex-col gap-2.5">
                        <p className="text-xs text-muted-foreground">
                          {questionAllowMultiple ? t('multipleChoicePrompt') : t('singleChoicePrompt')}
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {question.options.map((option) => (
                            <OptionPill
                              key={option.id}
                              label={option.label}
                              description={option.description}
                              selected={selected.includes(option.label)}
                              allowMultiple={questionAllowMultiple}
                              disabled={submitting}
                              onSelect={() => toggleFormOption(question.id, option.label, questionAllowMultiple)}
                            />
                          ))}
                        </div>
                      </div>
                    ) : null}

                    <textarea
                      className={clarificationTextareaClass}
                      rows={2}
                      placeholder={t('placeholder')}
                      value={questionText}
                      onChange={(e) =>
                        setFormTexts((prev) => ({
                          ...prev,
                          [question.id]: e.target.value,
                        }))
                      }
                      disabled={submitting}
                    />
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="flex flex-col gap-3 sm:gap-4">
              {options && options.length > 0 ? (
                <div className="flex flex-col gap-2.5 rounded-xl border border-border/60 bg-background/70 p-3 sm:p-4">
                  <p className="text-xs text-muted-foreground">
                    {allowMultiple ? t('multipleChoicePrompt') : t('singleChoicePrompt')}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {options.map((opt) => (
                      <OptionPill
                        key={opt}
                        label={opt}
                        selected={selectedOptions.includes(opt)}
                        allowMultiple={Boolean(allowMultiple)}
                        disabled={submitting}
                        onSelect={() => toggleOption(opt)}
                      />
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground">{t('optionalNote')}</p>
                </div>
              ) : null}

              <textarea
                className={clarificationTextareaClass}
                rows={options && options.length > 0 ? 2 : 3}
                placeholder={options && options.length > 0 ? t('freeTextWithOptionsPlaceholder') : t('placeholder')}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={submitting}
              />
            </div>
          )}

          {renderActions()}
        </div>
      </div>
    </div>
  );
};

export default React.memo(ClarificationInput);
