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
import { submitClarifyResponse } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import type { ClarificationForm } from '@/store/chat/types';

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
        await sendMessage('', messageId, undefined, null); // null means skip
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
      <div className="flex items-center gap-2 mt-3 px-3 py-2 bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 rounded-lg text-sm">
        <CheckCircleIcon className="w-4 h-4 text-green-500 shrink-0" />
        <span className="text-green-700 dark:text-green-300">{t('answered')}</span>
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

  return (
    <div className="mt-3 flex flex-col gap-3">
      {hasStructuredForm ? (
        <div className="flex flex-col gap-3 rounded-lg border border-border bg-muted/20 p-3">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {title ?? form?.title ?? t('formTitle')}
          </div>
          <div className="flex flex-col gap-3">
            {(form?.questions ?? []).map((question) => {
              const selected = formSelections[question.id] ?? [];
              const questionText = formTexts[question.id] ?? '';
              const questionAllowMultiple = question.allowMultiple ?? false;
              return (
                <div
                  key={question.id}
                  className="flex flex-col gap-3 rounded-lg border border-border bg-background p-3"
                >
                  <div className="text-sm font-medium text-foreground">{question.prompt}</div>

                  {question.options && question.options.length > 0 && (
                    <div className="flex flex-col gap-2">
                      <div className="text-xs text-muted-foreground">
                        {questionAllowMultiple ? t('multipleChoicePrompt') : t('singleChoicePrompt')}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {question.options.map((option) => {
                          const isSelected = selected.includes(option.label);
                          return (
                            <button
                              key={option.id}
                              type="button"
                              onClick={() => toggleFormOption(question.id, option.label, questionAllowMultiple)}
                              disabled={submitting}
                              className={`max-w-full rounded-full border px-3 py-2 text-left text-sm transition-all ${
                                isSelected
                                  ? 'border-primary bg-primary/10 text-primary'
                                  : 'border-border bg-background text-foreground hover:border-primary/50'
                              }`}
                            >
                              <div className="flex items-start gap-2">
                                <div
                                  className={`mt-0.5 flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-sm border ${
                                    isSelected ? 'border-primary bg-primary text-primary-foreground' : 'border-input'
                                  }`}
                                >
                                  {isSelected && (
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
                                  )}
                                </div>
                                <div className="flex flex-col gap-0.5">
                                  <span className="font-medium">{option.label}</span>
                                  {option.description ? (
                                    <span className="text-xs text-muted-foreground">{option.description}</span>
                                  ) : null}
                                </div>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  <textarea
                    className="w-full resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
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
        </div>
      ) : (
        <>
          {options && options.length > 0 && (
            <div className="flex flex-col gap-2 rounded-lg border border-border bg-muted/30 p-3">
              <div className="mb-1 text-xs text-muted-foreground">
                {allowMultiple ? t('multipleChoicePrompt') : t('singleChoicePrompt')}
              </div>
              <div className="flex flex-wrap gap-2">
                {options.map((opt) => {
                  const isSelected = selectedOptions.includes(opt);
                  return (
                    <button
                      key={opt}
                      type="button"
                      onClick={() => toggleOption(opt)}
                      disabled={submitting}
                      className={`rounded-full border px-3 py-1.5 text-left text-sm transition-all ${
                        isSelected
                          ? 'border-primary bg-primary/10 font-medium text-primary'
                          : 'border-border bg-background text-foreground hover:border-primary/50'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <div
                          className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-sm border ${
                            isSelected ? 'border-primary bg-primary text-primary-foreground' : 'border-input'
                          }`}
                        >
                          {isSelected && (
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
                          )}
                        </div>
                        <span>{opt}</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <textarea
            className="w-full resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
            rows={2}
            placeholder={options && options.length > 0 ? t('freeTextWithOptionsPlaceholder') : t('placeholder')}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={submitting}
          />
        </>
      )}

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={handleSkip}
          disabled={submitting}
          className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent disabled:opacity-50"
        >
          <SkipIcon className="h-3.5 w-3.5" />
          {t('skip')}
        </button>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={isSubmitDisabled}
          className="inline-flex items-center gap-1.5 rounded-full bg-primary px-3 py-1.5 text-xs text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
        >
          <SendIcon className="h-3.5 w-3.5" />
          {t('submit')}
        </button>
      </div>
    </div>
  );
};

export default React.memo(ClarificationInput);
