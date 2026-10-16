/**
 * [INPUT]
 * - @/store/chat/hitlAnswerRecord::summarizeClarificationRecord (POS: what a settled card shows of its answer)
 * - ./HitlAnsweredNote (POS: the banner this note is worded into)
 *
 * [OUTPUT]
 * - ClarificationSettledNote: the banner of a settled clarification card
 *
 * [POS]
 * Wording of a settled card from its answer record. A card settled before records existed, or whose record does not fit
 * it, shows the plain answered label. A form that asked for sign-off says it was not approved when nobody answered, and
 * points to the assistant's reply when a late answer was refused because the card had already been settled elsewhere.
 */

import React from 'react';
import { useTranslations } from 'next-intl';
import { summarizeClarificationRecord } from '@/store/chat/hitlAnswerRecord';
import type { ClarificationForm, HitlAnswerRecord } from '@/store/chat/types';

import HitlAnsweredNote from './HitlAnsweredNote';

export const ClarificationSettledNote = React.memo(function ClarificationSettledNote({
  answerRecord,
  form,
}: {
  answerRecord?: HitlAnswerRecord;
  form?: ClarificationForm;
}) {
  const t = useTranslations('chat.clarification');
  const outcome = summarizeClarificationRecord(answerRecord, form);

  // Silence is never consent: a sign-off form that went unanswered was not approved, rather than continued past.
  const needsSignOff = form?.requiresConfirmation === true;

  if (outcome?.kind === 'timeout') {
    return (
      <HitlAnsweredNote tone="muted" headline={t(needsSignOff ? 'answeredTimeoutUnconfirmed' : 'answeredTimeout')} />
    );
  }
  if (outcome?.kind === 'handled') {
    return <HitlAnsweredNote tone="muted" headline={t(needsSignOff ? 'answeredHandledSignOff' : 'answeredHandled')} />;
  }
  if (outcome?.kind === 'skipped') {
    return (
      <HitlAnsweredNote tone="muted" headline={t(needsSignOff ? 'answeredSkippedUnconfirmed' : 'answeredSkipped')} />
    );
  }
  return <HitlAnsweredNote tone="done" headline={t('answered')} lines={outcome?.lines} />;
});
