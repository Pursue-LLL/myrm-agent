'use client';

/**
 * [INPUT]
 * @phosphor-icons/react::PencilSimpleLine, TrashSimple
 * @/store/memory::PendingMemory (POS: Memory-domain types and store re-export entry)
 *
 * [OUTPUT]
 * PendingTargetHint: 纠正/删除类待审批提案的目标记忆披露块（新增类提案不渲染）
 *
 * [POS]
 * 待审批卡片与审批弹窗共用的披露块，让用户在确认前看到将被替换或移除的已有记忆。
 */

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { PencilSimpleLine, TrashSimple } from '@phosphor-icons/react';
import { cn } from '@/lib/utils/classnameUtils';
import type { PendingMemory } from '@/store/memory';

interface PendingTargetHintProps {
  memory: Pick<PendingMemory, 'resolution_action' | 'target_content'>;
  /** Clamp the target excerpt for compact cards; the review dialog shows it in full. */
  clamp?: boolean;
  className?: string;
}

const PendingTargetHint = memo<PendingTargetHintProps>(({ memory, clamp = false, className }) => {
  const t = useTranslations('memory');
  const { resolution_action: action, target_content: targetContent } = memory;
  if (action !== 'correct' && action !== 'delete') {
    return null;
  }

  const isDelete = action === 'delete';
  const Icon = isDelete ? TrashSimple : PencilSimpleLine;

  return (
    <div
      data-testid="pending-target-hint"
      className={cn(
        'rounded-lg border px-3 py-2 text-xs',
        isDelete
          ? 'border-destructive/20 bg-destructive/5 text-destructive'
          : 'border-amber-500/20 bg-amber-500/5 text-amber-600 dark:text-amber-400',
        className,
      )}
    >
      <div className="flex items-center gap-1.5 font-medium">
        <Icon size={12} weight="bold" aria-hidden="true" className="shrink-0" />
        <span>{isDelete ? t('fields.willDelete') : t('fields.willCorrect')}</span>
      </div>
      {targetContent && (
        <p className={cn('mt-1 leading-relaxed text-muted-foreground/80', clamp && 'line-clamp-2')}>
          <span className="font-medium">{t('fields.targetContent')}:</span> {targetContent}
        </p>
      )}
    </div>
  );
});

PendingTargetHint.displayName = 'PendingTargetHint';

export default PendingTargetHint;
