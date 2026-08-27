'use client';

/**
 * [INPUT]
 * @/components/features/memory/cards/MemoryScopeHierarchyCard::MemoryScopeLevel (POS: Scope level type)
 * next-intl::useTranslations (POS: i18n)
 *
 * [OUTPUT]
 * MemoryScopePicker: Segmented/Card control for selecting target memory scope (Task / Conversation / Agent / Global)
 * with inline recommendations, lifecycle descriptions, and clean border accents.
 *
 * [POS]
 * High-cohesion scope picker usable in MemoryCreateDialog, MemoryEditDialog, and PendingMemoryDialog.
 */

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { MemoryScopeLevel } from './MemoryScopeHierarchyCard';
import {
  IconClock,
  IconMessageSquare,
  IconCpu,
  IconGlobe,
} from '@/components/features/icons/PremiumIcons';

interface MemoryScopePickerProps {
  value: MemoryScopeLevel;
  onChange: (value: MemoryScopeLevel) => void;
  disabled?: boolean;
  className?: string;
  showHint?: boolean;
}

const SCOPE_OPTIONS: {
  level: MemoryScopeLevel;
  labelKey: string;
  hintKey: string;
  icon: typeof IconGlobe;
}[] = [
  {
    level: 'task',
    labelKey: 'scopePicker.taskLabel',
    hintKey: 'scopePicker.taskHint',
    icon: IconClock,
  },
  {
    level: 'conversation',
    labelKey: 'scopePicker.conversationLabel',
    hintKey: 'scopePicker.conversationHint',
    icon: IconMessageSquare,
  },
  {
    level: 'agent',
    labelKey: 'scopePicker.agentLabel',
    hintKey: 'scopePicker.agentHint',
    icon: IconCpu,
  },
  {
    level: 'global',
    labelKey: 'scopePicker.globalLabel',
    hintKey: 'scopePicker.globalHint',
    icon: IconGlobe,
  },
];

export const MemoryScopePicker = memo<MemoryScopePickerProps>(({
  value,
  onChange,
  disabled = false,
  className,
  showHint = true,
}) => {
  const t = useTranslations('memory');

  return (
    <div className={cn('space-y-2', className)}>
      <div className="flex items-center justify-between">
        <label className="text-xs font-medium text-foreground">{t('scopePicker.label')}</label>
        {showHint && (
          <span className="text-[11px] text-muted-foreground">
            {t(`scopePicker.${value}Hint`)}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {SCOPE_OPTIONS.map((opt) => {
          const Icon = opt.icon;
          const isSelected = value === opt.level;

          return (
            <button
              type="button"
              key={opt.level}
              disabled={disabled}
              onClick={() => onChange(opt.level)}
              className={cn(
                'flex items-center gap-2 rounded-lg border px-2.5 py-2 text-left transition-all',
                disabled ? 'cursor-not-allowed opacity-60' : 'hover:border-primary/40 hover:bg-accent/20',
                isSelected
                  ? 'border-primary bg-primary/10 text-primary font-medium ring-1 ring-primary/20'
                  : 'border-border/60 bg-background/50 text-muted-foreground',
              )}
            >
              <Icon className={cn('h-3.5 w-3.5 shrink-0', isSelected ? 'text-primary' : 'text-muted-foreground')} />
              <div className="min-w-0 flex-1 truncate text-xs">{t(opt.labelKey)}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
});

MemoryScopePicker.displayName = 'MemoryScopePicker';

export default MemoryScopePicker;
