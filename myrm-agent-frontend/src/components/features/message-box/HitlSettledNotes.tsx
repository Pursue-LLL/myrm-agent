/**
 * [INPUT]
 * - @/store/chat/hitlAnswerRecord::summarizeClarificationRecord / summarizeDirectoryRecord (POS: what a settled card shows of its answer)
 * - ./HitlAnsweredNote (POS: the banner these notes are worded into)
 *
 * [OUTPUT]
 * - ClarificationSettledNote / DirectorySettledNote: the banner of a settled clarification or directory card
 *
 * [POS]
 * Wording of a settled card from its answer record. A card settled before records existed, or whose record does not fit
 * it, shows the plain answered label.
 */

import React from 'react';
import { useTranslations } from 'next-intl';
import { summarizeClarificationRecord, summarizeDirectoryRecord } from '@/store/chat/hitlAnswerRecord';
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

  if (outcome?.kind === 'timeout') {
    return <HitlAnsweredNote tone="muted" headline={t('answeredTimeout')} />;
  }
  if (outcome?.kind === 'skipped') {
    return <HitlAnsweredNote tone="muted" headline={t('answeredSkipped')} />;
  }
  return <HitlAnsweredNote tone="done" headline={t('answered')} lines={outcome?.lines} />;
});

export const DirectorySettledNote = React.memo(function DirectorySettledNote({
  answerRecord,
}: {
  answerRecord?: HitlAnswerRecord;
}) {
  const t = useTranslations('chat.directoryRequest');
  const outcome = summarizeDirectoryRecord(answerRecord);

  switch (outcome?.kind) {
    case 'granted':
      return (
        <HitlAnsweredNote
          tone="done"
          headline={t(outcome.writable ? 'grantedWritable' : 'grantedReadOnly')}
          lines={[{ key: 'path', text: outcome.path }]}
        />
      );
    case 'denied':
      return <HitlAnsweredNote tone="muted" headline={t('denied')} />;
    case 'timeout':
      return <HitlAnsweredNote tone="muted" headline={t('timedOut')} />;
    default:
      return <HitlAnsweredNote tone="done" headline={t('answered')} />;
  }
});
