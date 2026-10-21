'use client';

/**
 * [INPUT]
 * @/store/chat/types::ClarificationForm (POS: structured clarification form schema)
 * @/services/chat::submitClarifyResponse (POS: clarification answer submission API)
 * @/store/useChatStore::sendMessage (POS: resume-mode clarification send path)
 * @/store/chat/clarificationCardAnswer::answerClarificationWithResume / settleClarificationCard (POS: the card closes at click so the composer is released for the resumed run, and reopens when the resume is not delivered)
 * @/store/chat/clarificationCardDraft::loadClarificationDraft (POS: what the user had written when a refused resume brings the card back)
 * @/store/chat/streamErrors::ApprovalAlreadyResolvedError (POS: the timeout or another device already settled the card without this answer)
 * ./ClarificationOptions, ./ClarificationChrome (POS: option-list and card-shell presentation primitives)
 * ./ClarificationSettledNote (POS: the banner the card collapses into once settled)
 *
 * [OUTPUT]
 * ClarificationInput: Renders single-question and structured clarification forms.
 * Structured answers submit option.id values keyed by question.id for agent resume contract.
 * A settled card shows whether it was answered, skipped, timed out or already handled elsewhere, and the answer given.
 *
 * [POS]
 * Chat clarification answer surface. Bridges assistant clarification messages to
 * user input and the appropriate submission path.
 */

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { submitClarifyResponse } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { answerClarificationWithResume, settleClarificationCard } from '@/store/chat/clarificationCardAnswer';
import { loadClarificationDraft } from '@/store/chat/clarificationCardDraft';
import { ApprovalAlreadyResolvedError } from '@/store/chat/streamErrors';
import type { ClarificationForm, HitlAnswerRecord } from '@/store/chat/types';
import { isImeComposing } from '@/lib/utils/imeUtils';
import {
  buildSingleClarificationAnswer,
  buildStructuredClarificationAnswer,
  type ClarificationAnswer,
} from './clarificationAnswer';
import {
  SendIcon,
  SkipIcon,
  clarificationTextareaClass,
  resolveClarificationBadgeClass,
  resolveClarificationGradientClass,
  resolveClarificationShellClass,
} from './ClarificationChrome';
import { COLLAPSED_OPTIONS_LIMIT, ExpandToggle, OptionPill } from './ClarificationOptions';
import { ClarificationSettledNote } from './ClarificationSettledNote';

interface ClarificationInputProps {
  messageId: string;
  answered: boolean;
  options?: string[];
  allowMultiple?: boolean;
  title?: string;
  form?: ClarificationForm;
  isResumeMode?: boolean;
  answerRecord?: HitlAnswerRecord;
  variant?: 'inline' | 'composer';
}

const ClarificationInput = ({
  messageId,
  answered,
  options,
  allowMultiple,
  title,
  form,
  isResumeMode,
  answerRecord,
  variant = 'inline',
}: ClarificationInputProps) => {
  const t = useTranslations('chat.clarification');
  const [draft] = useState(() => loadClarificationDraft(messageId));
  const [input, setInput] = useState(draft?.input ?? '');
  const [submitting, setSubmitting] = useState(false);
  const [selectedOptions, setSelectedOptions] = useState<string[]>(draft?.selectedOptions ?? []);
  const [formTexts, setFormTexts] = useState<Record<string, string>>(draft?.formTexts ?? {});
  const [formSelections, setFormSelections] = useState<Record<string, string[]>>(draft?.formSelections ?? {});
  const [expandedQuestions, setExpandedQuestions] = useState<Record<string, boolean>>({});
  const [isSimpleOptionsExpanded, setIsSimpleOptionsExpanded] = useState(false);
  const hasStructuredForm = Boolean(form?.questions && form.questions.length > 0);
  const sendMessage = useChatStore((state) => state.sendMessage);

  const toggleQuestionExpand = (questionId: string) => {
    setExpandedQuestions((prev) => ({
      ...prev,
      [questionId]: !prev[questionId],
    }));
  };

  // An answer that arrives after the timeout or another device already settled the card is not a failure: the card
  // stays closed.
  const reportAnswerError = (err: unknown) => {
    if (err instanceof ApprovalAlreadyResolvedError) {
      toast.warning(t('alreadyHandled'));
      return;
    }
    console.error('Failed to answer clarification:', err);
    toast.error(t('submitFailed'));
  };

  const toggleOption = (opt: string) => {
    if (allowMultiple) {
      setSelectedOptions((prev) => (prev.includes(opt) ? prev.filter((item) => item !== opt) : [...prev, opt]));
      return;
    }
    setSelectedOptions([opt]);
  };

  const toggleFormOption = (questionId: string, optionId: string, questionAllowMultiple: boolean) => {
    setFormSelections((prev) => {
      const current = prev[questionId] ?? [];
      const next = questionAllowMultiple
        ? current.includes(optionId)
          ? current.filter((item) => item !== optionId)
          : [...current, optionId]
        : [optionId];
      return { ...prev, [questionId]: next };
    });
  };

  // Resume mode closes the card at click because the request streams the whole resumed run; the legacy clarify API is
  // a short call, so its card closes once the server accepted the answer.
  const submitAnswer = async (resumeValue: ClarificationAnswer, legacyAnswer: ClarificationAnswer) => {
    setSubmitting(true);
    try {
      if (isResumeMode) {
        await answerClarificationWithResume(
          messageId,
          { value: resumeValue, draft: { input, selectedOptions, formTexts, formSelections } },
          () => sendMessage('', messageId, undefined, resumeValue),
        );
      } else {
        await submitClarifyResponse(messageId, legacyAnswer);
        settleClarificationCard(messageId, { by: 'user', value: legacyAnswer });
      }
    } catch (err) {
      reportAnswerError(err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = async () => {
    if (submitting) {
      return;
    }
    const finalAnswer = hasStructuredForm
      ? buildStructuredClarificationAnswer(form, formSelections, formTexts)
      : buildSingleClarificationAnswer(input, selectedOptions);
    if (!finalAnswer) {
      return;
    }
    await submitAnswer(finalAnswer, finalAnswer);
  };

  const handleSkip = async () => {
    if (submitting) {
      return;
    }
    await submitAnswer({}, '');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (isImeComposing(e)) {
      return;
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  if (answered) {
    return <ClarificationSettledNote answerRecord={answerRecord} form={form} />;
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
  const requiresConfirmation = form?.requiresConfirmation;
  const clarificationContext = form?.context;
  const questionCount = form?.questions.length ?? 0;
  const badgeLabel = requiresConfirmation ? t('riskBadge') : t('badge');

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
    <div
      className={variant === 'composer' ? 'mt-0' : 'mt-3 sm:mt-4'}
      data-clarification-form={hasStructuredForm ? 'structured' : 'simple'}
    >
      <div className={resolveClarificationShellClass(requiresConfirmation)}>
        <div className={resolveClarificationGradientClass(requiresConfirmation)} />

        <div className="relative flex flex-col gap-4 p-3 sm:gap-5 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex min-w-0 flex-col gap-1">
              <span className="text-sm font-semibold leading-snug text-foreground sm:text-base">{displayTitle}</span>
              {clarificationContext ? (
                <span className="text-xs leading-relaxed text-muted-foreground">{clarificationContext}</span>
              ) : null}
              {hasStructuredForm && questionCount > 1 ? (
                <span className="text-xs text-muted-foreground">{t('questionCount', { count: questionCount })}</span>
              ) : null}
            </div>
            <span className={resolveClarificationBadgeClass(requiresConfirmation)}>{badgeLabel}</span>
          </div>

          {hasStructuredForm ? (
            <div className="flex flex-col gap-3 sm:gap-4">
              {(form?.questions ?? []).map((question, index) => {
                const selected = formSelections[question.id] ?? [];
                const questionText = formTexts[question.id] ?? '';
                const questionAllowMultiple = question.allowMultiple ?? false;
                const hasQuestionOptions = Boolean(question.options && question.options.length > 0);
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
                      <p className="text-sm font-medium leading-relaxed text-foreground sm:text-[15px]">
                        {question.prompt}
                      </p>
                    </div>

                    {question.options && question.options.length > 0
                      ? (() => {
                          const totalOptions = question.options.length;
                          const hasSelectedInHidden =
                            totalOptions > COLLAPSED_OPTIONS_LIMIT &&
                            question.options.slice(COLLAPSED_OPTIONS_LIMIT).some((opt) => selected.includes(opt.id));
                          const isExpanded = Boolean(expandedQuestions[question.id]) || hasSelectedInHidden;
                          const visibleOptions =
                            !isExpanded && totalOptions > COLLAPSED_OPTIONS_LIMIT
                              ? question.options.slice(0, COLLAPSED_OPTIONS_LIMIT)
                              : question.options;

                          return (
                            <div className="flex flex-col gap-2.5">
                              <p className="text-xs text-muted-foreground">
                                {questionAllowMultiple ? t('multipleChoicePrompt') : t('singleChoicePrompt')}
                              </p>
                              <div className="flex flex-wrap gap-2">
                                {visibleOptions.map((option) => (
                                  <OptionPill
                                    key={option.id}
                                    label={option.label}
                                    description={option.description}
                                    selected={selected.includes(option.id)}
                                    allowMultiple={questionAllowMultiple}
                                    disabled={submitting}
                                    onSelect={() => toggleFormOption(question.id, option.id, questionAllowMultiple)}
                                    recommendedBadgeText={t('recommendedBadge')}
                                  />
                                ))}
                              </div>
                              {totalOptions > COLLAPSED_OPTIONS_LIMIT ? (
                                <ExpandToggle
                                  expanded={isExpanded}
                                  label={
                                    isExpanded
                                      ? t('collapseOptions')
                                      : t('expandOptions', { count: totalOptions - COLLAPSED_OPTIONS_LIMIT })
                                  }
                                  onToggle={() => toggleQuestionExpand(question.id)}
                                />
                              ) : null}
                            </div>
                          );
                        })()
                      : null}

                    {hasQuestionOptions ? <p className="text-xs text-muted-foreground">{t('optionalNote')}</p> : null}

                    <textarea
                      className={clarificationTextareaClass}
                      rows={2}
                      placeholder={hasQuestionOptions ? t('freeTextWithOptionsPlaceholder') : t('placeholder')}
                      value={questionText}
                      onChange={(e) =>
                        setFormTexts((prev) => ({
                          ...prev,
                          [question.id]: e.target.value,
                        }))
                      }
                      onKeyDown={handleKeyDown}
                      disabled={submitting}
                    />
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="flex flex-col gap-3 sm:gap-4">
              {options && options.length > 0
                ? (() => {
                    const totalSimpleOptions = options.length;
                    const hasSelectedInHidden =
                      totalSimpleOptions > COLLAPSED_OPTIONS_LIMIT &&
                      options.slice(COLLAPSED_OPTIONS_LIMIT).some((opt) => selectedOptions.includes(opt));
                    const effectiveExpanded = isSimpleOptionsExpanded || hasSelectedInHidden;
                    const visibleSimpleOptions =
                      !effectiveExpanded && totalSimpleOptions > COLLAPSED_OPTIONS_LIMIT
                        ? options.slice(0, COLLAPSED_OPTIONS_LIMIT)
                        : options;

                    return (
                      <div className="flex flex-col gap-2.5 rounded-xl border border-border/60 bg-background/70 p-3 sm:p-4">
                        <p className="text-xs text-muted-foreground">
                          {allowMultiple ? t('multipleChoicePrompt') : t('singleChoicePrompt')}
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {visibleSimpleOptions.map((opt) => (
                            <OptionPill
                              key={opt}
                              label={opt}
                              selected={selectedOptions.includes(opt)}
                              allowMultiple={Boolean(allowMultiple)}
                              disabled={submitting}
                              onSelect={() => toggleOption(opt)}
                              recommendedBadgeText={t('recommendedBadge')}
                            />
                          ))}
                        </div>
                        {totalSimpleOptions > COLLAPSED_OPTIONS_LIMIT ? (
                          <ExpandToggle
                            expanded={effectiveExpanded}
                            label={
                              effectiveExpanded
                                ? t('collapseOptions')
                                : t('expandOptions', { count: totalSimpleOptions - COLLAPSED_OPTIONS_LIMIT })
                            }
                            onToggle={() => setIsSimpleOptionsExpanded((prev) => !prev)}
                          />
                        ) : null}
                        <p className="text-xs text-muted-foreground">{t('optionalNote')}</p>
                      </div>
                    );
                  })()
                : null}

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
