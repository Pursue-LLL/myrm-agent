'use client';

import { memo } from 'react';
import type { ApplyStatus } from '@/store/retrieval/types';
import { useApplyMessage } from './applyMessage';

const OUTCOME_CLASS: Record<ApplyStatus, string> = {
  idle: 'text-muted-foreground',
  applying: 'text-muted-foreground',
  success: 'text-green-600 dark:text-green-400',
  error: 'text-red-600 dark:text-red-400',
};

interface ApplyOutcomeProps {
  status: ApplyStatus;
  /** Raw (English) message recorded by the store; shown localised. */
  message?: string;
}

/** The outcome line under an apply control: nothing until an apply has run. */
const ApplyOutcome = memo<ApplyOutcomeProps>(({ status, message }) => {
  const text = useApplyMessage()(message);

  if (!text || status === 'idle') {
    return null;
  }
  return <p className={`text-xs ${OUTCOME_CLASS[status]}`}>{text}</p>;
});

ApplyOutcome.displayName = 'ApplyOutcome';

export default ApplyOutcome;
