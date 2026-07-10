'use client';

/**
 * [INPUT]
 * @/services/chat::submitPlanConfirmResponse (POS: plan confirm API)
 * @/store/chat/types::Message.planConfirmation (POS: plan confirmation state)
 *
 * [OUTPUT]
 * PlanConfirmationCard: Renders research plan review card with confirm/edit/skip actions.
 *
 * [POS]
 * Deep Research plan confirmation HITL gate. Shows the AI-generated research plan
 * and lets the user approve, edit, or skip before execution begins.
 */

import React, { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { submitPlanConfirmResponse } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { cn } from '@/lib/utils';

interface PlanConfirmationCardProps {
  messageId: string;
  plan: string;
  status: 'waiting' | 'confirmed' | 'edited' | 'skipped';
}

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

const PencilIcon = ({ className }: { className?: string }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
    <path d="m15 5 4 4" />
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

const resolvedStatusMap: Record<string, string> = {
  confirmed: 'confirmed',
  edited: 'edited',
  skipped: 'skipped',
};

const PlanConfirmationCard = ({ messageId, plan, status }: PlanConfirmationCardProps) => {
  const t = useTranslations('chat.planConfirmation');
  const [editing, setEditing] = useState(false);
  const [editedPlan, setEditedPlan] = useState(plan);
  const [submitting, setSubmitting] = useState(false);

  const markResolved = useCallback(
    (resolvedStatus: 'confirmed' | 'edited' | 'skipped') => {
      useChatStore.setState((state) => {
        const idx = state.messages.findIndex((m) => m.messageId === messageId);
        if (idx !== -1 && state.messages[idx].planConfirmation) {
          state.messages[idx].planConfirmation!.status = resolvedStatus;
        }
      });
    },
    [messageId],
  );

  const handleConfirm = async () => {
    if (submitting) return;
    setSubmitting(true);
    try {
      await submitPlanConfirmResponse(messageId, 'confirm');
      markResolved('confirmed');
    } catch (err) {
      console.error('Failed to confirm plan:', err);
      toast.error(t('submitFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleEdit = async () => {
    if (submitting) return;
    if (!editing) {
      setEditing(true);
      return;
    }
    const trimmed = editedPlan.trim();
    if (!trimmed) return;
    setSubmitting(true);
    try {
      const isChanged = trimmed !== plan.trim();
      await submitPlanConfirmResponse(messageId, isChanged ? 'edit' : 'confirm', isChanged ? trimmed : undefined);
      markResolved(isChanged ? 'edited' : 'confirmed');
    } catch (err) {
      console.error('Failed to submit edited plan:', err);
      toast.error(t('submitFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleSkip = async () => {
    if (submitting) return;
    setSubmitting(true);
    try {
      await submitPlanConfirmResponse(messageId, 'skip');
      markResolved('skipped');
    } catch (err) {
      console.error('Failed to skip plan confirmation:', err);
      toast.error(t('submitFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  if (status !== 'waiting') {
    const label = resolvedStatusMap[status];
    return (
      <div className="mt-3 flex items-center gap-2.5 rounded-2xl border border-emerald-500/30 bg-emerald-500/5 px-3 py-2.5 text-sm sm:mt-4 sm:px-4 sm:py-3">
        <CheckCircleIcon className="h-4 w-4 shrink-0 text-emerald-500 dark:text-emerald-400" />
        <span className="font-medium text-emerald-700 dark:text-emerald-300">{label ? t(label) : t('confirmed')}</span>
      </div>
    );
  }

  return (
    <div className="mt-3 sm:mt-4">
      <div className="relative overflow-hidden rounded-2xl border border-blue-500/40 bg-card/90 backdrop-blur-xl">
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-blue-500/10 via-transparent to-cyan-500/5 dark:from-blue-500/15 dark:to-cyan-500/10" />

        <div className="relative flex flex-col gap-4 p-3 sm:gap-5 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex min-w-0 flex-col gap-1">
              <span className="text-sm font-semibold leading-snug text-foreground sm:text-base">{t('title')}</span>
              <span className="text-xs leading-relaxed text-muted-foreground">{t('description')}</span>
            </div>
            <span className="shrink-0 rounded-full border border-blue-500/30 bg-blue-500/10 px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide text-blue-700 dark:text-blue-300">
              {t('badge')}
            </span>
          </div>

          {editing ? (
            <textarea
              className="w-full resize-none rounded-xl border border-border/70 bg-background/90 px-3 py-2.5 font-mono text-sm leading-relaxed placeholder:text-muted-foreground transition-colors focus:border-blue-500/50 focus:outline-none focus:ring-2 focus:ring-blue-500/25 sm:px-4 sm:py-3"
              rows={Math.min(Math.max(editedPlan.split('\n').length + 1, 6), 20)}
              placeholder={t('editPlaceholder')}
              value={editedPlan}
              onChange={(e) => setEditedPlan(e.target.value)}
              disabled={submitting}
            />
          ) : (
            <div className="rounded-xl border border-border/60 bg-background/70 p-3 sm:p-4">
              <pre className="whitespace-pre-wrap font-mono text-sm leading-relaxed text-foreground/90">{plan}</pre>
            </div>
          )}

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
              onClick={handleEdit}
              disabled={submitting}
              className={cn(
                'inline-flex w-full items-center justify-center gap-1.5 rounded-full border px-4 py-2.5 text-sm font-medium transition-colors disabled:opacity-50 sm:w-auto sm:py-2',
                editing
                  ? 'border-blue-500/50 bg-blue-600 text-white hover:bg-blue-700'
                  : 'border-blue-500/30 bg-blue-500/10 text-blue-700 hover:bg-blue-500/20 dark:text-blue-300',
              )}
            >
              <PencilIcon className="h-3.5 w-3.5" />
              {t('edit')}
            </button>
            {!editing && (
              <button
                type="button"
                onClick={handleConfirm}
                disabled={submitting}
                className="inline-flex w-full items-center justify-center gap-1.5 rounded-full bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50 sm:w-auto sm:py-2"
              >
                <CheckCircleIcon className="h-3.5 w-3.5" />
                {t('confirm')}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default React.memo(PlanConfirmationCard);
