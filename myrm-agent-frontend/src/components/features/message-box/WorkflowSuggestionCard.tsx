'use client';

/**
 * [INPUT]
 * @/store/useChatStore (POS: workflow mode toggle)
 *
 * [OUTPUT]
 * WorkflowSuggestionCard: Non-blocking inline suggestion for DW Engine.
 *
 * [POS]
 * Workflow escalation hint. Shown when server detects a complex decomposable
 * task that would benefit from multi-agent parallel execution. Does NOT block
 * the standard agent stream — appears as an inline tip above the response.
 */

import React, { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import useChatStore from '@/store/useChatStore';
import { cn } from '@/lib/utils';
import { IconWorkflow } from '@/components/features/icons/PremiumIcons';

interface WorkflowSuggestionCardProps {
  messageId: string;
  status: 'suggested' | 'accepted' | 'dismissed';
}

const WorkflowSuggestionCard = ({ messageId, status }: WorkflowSuggestionCardProps) => {
  const t = useTranslations('chat.workflowSuggestion');
  const [dismissed, setDismissed] = useState(status === 'dismissed');

  const handleActivate = useCallback(() => {
    useChatStore.setState((state) => {
      const msg = state.messages.find((m) => m.messageId === messageId && m.role === 'assistant');
      if (msg?.workflowSuggestion) {
        msg.workflowSuggestion.status = 'accepted';
      }
    });
    useChatStore.getState().setIsWorkflowMode(true);
  }, [messageId]);

  const handleDismiss = useCallback(() => {
    setDismissed(true);
    useChatStore.setState((state) => {
      const msg = state.messages.find((m) => m.messageId === messageId && m.role === 'assistant');
      if (msg?.workflowSuggestion) {
        msg.workflowSuggestion.status = 'dismissed';
      }
    });
  }, [messageId]);

  if (dismissed || status === 'dismissed') {
    return null;
  }

  if (status === 'accepted') {
    return (
      <div className="mb-2 flex items-center gap-2 rounded-xl border border-primary/20 bg-primary/5 px-3 py-2 text-xs">
        <IconWorkflow className="shrink-0 text-primary" />
        <span className="text-primary/80 font-medium">{t('activated')}</span>
      </div>
    );
  }

  return (
    <div className="mb-2 flex flex-wrap items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/5 px-3 py-2 dark:border-amber-400/20 dark:bg-amber-500/10">
      <IconWorkflow className="shrink-0 text-amber-600 dark:text-amber-400" />
      <span className="min-w-0 flex-1 text-xs leading-relaxed text-amber-800 dark:text-amber-200">{t('hint')}</span>
      <div className="flex shrink-0 items-center gap-1.5">
        <button
          type="button"
          onClick={handleDismiss}
          className="rounded-md px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-muted/60"
        >
          {t('dismiss')}
        </button>
        <button
          type="button"
          onClick={handleActivate}
          className={cn(
            'inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors',
            'bg-primary/10 text-primary hover:bg-primary/20',
          )}
        >
          {t('activate')}
        </button>
      </div>
    </div>
  );
};

export default React.memo(WorkflowSuggestionCard);
