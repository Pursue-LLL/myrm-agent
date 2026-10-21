'use client';

/**
 * [INPUT]
 * - @/lib/chat/progressStepsUi::expandProgressStepsForMessage
 *
 * [OUTPUT]
 * - SkillManageUndoHintCard: user-facing hint to open Task Steps and undo skill edits
 *
 * [POS]
 * Chat message affordance when a successful skill_manage batch is present in progress steps.
 */

import { memo } from 'react';
import { Undo2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { expandProgressStepsForMessage } from '@/lib/chat/progressStepsUi';

type SkillManageUndoHintCardProps = {
  messageId: string;
};

export const SkillManageUndoHintCard = memo<SkillManageUndoHintCardProps>(({ messageId }) => {
  const t = useTranslations('progressSteps');

  return (
    <div
      className={cn(
        'mt-3 w-full max-w-md overflow-hidden rounded-xl border border-primary/25 bg-primary/5',
        'text-sm text-foreground shadow-sm',
      )}
      data-testid="skill-manage-undo-hint"
    >
      <div className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-2.5">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
            <Undo2 className="h-4 w-4" aria-hidden />
          </span>
          <p className="min-w-0 leading-relaxed text-foreground/90">{t('skillManageUndoHintBody')}</p>
        </div>
        <button
          type="button"
          className={cn(
            'btn-brand-elevation shrink-0 rounded-full px-4 py-2 text-xs font-medium',
            'bg-primary text-primary-foreground hover:bg-primary-hover',
          )}
          data-testid="skill-manage-undo-hint-open-steps"
          onClick={() => expandProgressStepsForMessage(messageId)}
        >
          {t('skillManageUndoHintAction')}
        </button>
      </div>
    </div>
  );
});

SkillManageUndoHintCard.displayName = 'SkillManageUndoHintCard';
