'use client';

import { useRef } from 'react';
import type { useTranslations } from 'next-intl';
import { readSendOrigin, sendGoalReviewFeedback } from '@/components/features/message-box/userMessageResend';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { isImeComposing } from '@/lib/utils/imeUtils';
import { AlertIcon, CheckCircleIcon } from './goal-icons';

interface GoalHumanReviewActionProps {
  /** Resolves whether the server took the action. */
  onAction: (action: 'approve' | 'reject', note?: string) => Promise<boolean>;
  t: ReturnType<typeof useTranslations>;
}

export function GoalHumanReviewAction({ onAction, t }: GoalHumanReviewActionProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const sending = useRef(false);

  // The goal goes back to work before the feedback is sent, since the agent reads only a goal that is active. The
  // server holds the feedback when a risk rule holds it, and the goal then stays in review with the text in the box
  // to be edited. One reject at a time: a second submit while the request is out would send the feedback twice.
  const rejectWithFeedback = async () => {
    const input = inputRef.current;
    if (!input || sending.current) {
      return;
    }
    sending.current = true;
    // The chat the review belongs to, before the request is out: the user may open another chat while it is.
    const origin = readSendOrigin();
    const typed = input.value;
    const feedback = typed.trim() ? typed : t('resetRetriesMessage');
    try {
      if (!(await onAction('reject', feedback))) {
        return;
      }
      // Text typed while the request was out is not the one that was taken, so it stays.
      if (input.value === typed) {
        input.value = '';
      }
      // Fire and forget: the send settles when the whole turn has ended, long after the panel is gone.
      void sendGoalReviewFeedback(origin, feedback);
    } finally {
      sending.current = false;
    }
  };

  return (
    <div className="mt-4 p-3 bg-orange-500/10 border border-orange-500/20 rounded-lg">
      <div className="flex items-center gap-2 mb-2">
        <AlertIcon className="h-4 w-4 text-orange-600" />
        <p className="text-sm text-orange-600 font-medium">{t('reviewFailedMessage')}</p>
      </div>
      <p className="text-xs text-orange-600/80 mb-3">{t('reviewFailedHint')}</p>
      <div className="flex flex-col gap-2">
        <div className="flex gap-2">
          <Input
            ref={inputRef}
            placeholder={t('feedbackPlaceholder')}
            className="h-8 text-xs bg-background/50 border-orange-200 focus-visible:ring-orange-500"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !isImeComposing(e)) {
                void rejectWithFeedback();
              }
            }}
          />
          <Button
            size="sm"
            variant="outline"
            className="border-orange-200 hover:bg-orange-50 text-orange-700 shrink-0"
            onClick={(e) => {
              e.stopPropagation();
              void rejectWithFeedback();
            }}
          >
            {t('rejectAndRetry')}
          </Button>
        </div>
        <Button
          size="sm"
          className="w-full bg-green-500 hover:bg-green-600 text-white"
          onClick={(e) => {
            e.stopPropagation();
            void onAction('approve');
          }}
        >
          <CheckCircleIcon className="h-4 w-4 mr-1" />
          {t('forceApprove')}
        </Button>
      </div>
    </div>
  );
}
