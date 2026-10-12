'use client';

/**
 * [INPUT]
 * @/store/memory::Memory (POS: Frontend Memory Model)
 *
 * [OUTPUT]
 * MemoryProceduralDetails: Component rendering trigger, action, and rationale for procedural rules.
 *
 * [POS]
 * UI presenter for procedural behavioral rules in memory cards.
 */

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { Zap } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { Memory } from '@/store/memory';

interface MemoryProceduralDetailsProps {
  confirmed: Memory;
}

export const MemoryProceduralDetails = memo<MemoryProceduralDetailsProps>(({ confirmed }) => {
  const t = useTranslations('memory');

  if (confirmed.memory_type !== 'procedural' || !confirmed.trigger) {
    return null;
  }

  return (
    <div className="mt-2 space-y-1 text-xs text-muted-foreground">
      <div className="flex items-center gap-1.5 flex-wrap">
        <Zap size={12} className="text-amber-500 shrink-0" />
        <span>
          {t('fields.trigger')}: {confirmed.trigger}
        </span>
        {confirmed.tool_name && (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-primary/10 text-primary text-[10px] font-medium">
            {confirmed.tool_name}
          </span>
        )}
        {confirmed.tool_rule_priority && confirmed.tool_rule_priority !== 'normal' && (
          <span
            className={cn(
              'inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium',
              confirmed.tool_rule_priority === 'critical'
                ? 'bg-destructive/10 text-destructive'
                : 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
            )}
          >
            {confirmed.tool_rule_priority.toUpperCase()}
          </span>
        )}
      </div>

      {confirmed.action && (
        <div className="flex items-center gap-1.5 pl-[18px]">
          <span>
            {t('fields.action')}: {confirmed.action}
          </span>
        </div>
      )}

      {confirmed.expected_valid_days !== undefined &&
        confirmed.expected_valid_days !== null &&
        !confirmed.is_user_locked && (
          <div className="flex items-center gap-1.5 pl-[18px] text-muted-foreground/80 mt-0.5">
            <span className="italic">
              <span className="font-medium mr-1">{t('fields.ttlDays', { days: confirmed.expected_valid_days })}</span>
            </span>
          </div>
        )}

      {confirmed.reasoning && (
        <div className="flex items-center gap-1.5 pl-[18px] text-muted-foreground/80 mt-0.5">
          <span className="italic">
            <span className="font-medium mr-1">{t('fields.reasoning')}:</span> {confirmed.reasoning}
          </span>
        </div>
      )}

      {confirmed.application && (
        <div className="flex items-center gap-1.5 pl-[18px] text-muted-foreground/80 mt-0.5">
          <span className="italic">
            <span className="font-medium mr-1">{t('fields.application')}:</span> {confirmed.application}
          </span>
        </div>
      )}
    </div>
  );
});

MemoryProceduralDetails.displayName = 'MemoryProceduralDetails';
