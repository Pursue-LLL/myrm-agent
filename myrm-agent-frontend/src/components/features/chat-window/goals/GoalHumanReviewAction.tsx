'use client';

import { useRef } from 'react';
import type { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { isImeComposing } from '@/lib/utils/imeUtils';
import { showI18nToast } from '@/services/i18nToastService';
import useChatStore from '@/store/useChatStore';
import { AlertIcon, CheckCircleIcon } from './goal-icons';

interface GoalHumanReviewActionProps {
  onAction: (action: 'approve' | 'reject', note?: string) => void;
  t: ReturnType<typeof useTranslations>;
}

/** The store explains a refused send itself; only a rejected send (the agent is still busy, or it failed) is reported here. */
function notifyFeedbackNotSent(error: unknown): void {
  if (error instanceof Error && error.name === 'AgentBusyError') {
    showI18nToast('chat.sendBlocked.title', undefined, {
      descriptionKey: 'chat.sendBlocked.busyDescription',
      type: 'warning',
      duration: 3000,
    });
    return;
  }
  console.error('[GoalHumanReviewAction] feedback not sent:', error);
  showI18nToast('chat.messageFailed.title', undefined, {
    descriptionKey: 'chat.messageFailed.generic',
    type: 'error',
    duration: 3000,
  });
}

export function GoalHumanReviewAction({ onAction, t }: GoalHumanReviewActionProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const sending = useRef(false);

  // The goal leaves review, and the feedback leaves the box, only once the agent took the message: a send that was
  // held (risk rule), refused or failed keeps the goal waiting for a decision and the text there to be edited.
  // One send at a time: a second submit while the request is out would send the same feedback twice.
  const rejectWithFeedback = async () => {
    const input = inputRef.current;
    if (!input || sending.current) {
      return;
    }
    sending.current = true;
    const typed = input.value;
    try {
      const dispatched = await useChatStore.getState().sendMessage(typed.trim() ? typed : t('resetRetriesMessage'));
      if (dispatched) {
        onAction('reject');
        // Text typed while the request was out is not the one that was taken, so it stays.
        if (input.value === typed) {
          input.value = '';
        }
      }
    } catch (error) {
      notifyFeedbackNotSent(error);
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
            onAction('approve');
          }}
        >
          <CheckCircleIcon className="h-4 w-4 mr-1" />
          {t('forceApprove')}
        </Button>
      </div>
    </div>
  );
}
