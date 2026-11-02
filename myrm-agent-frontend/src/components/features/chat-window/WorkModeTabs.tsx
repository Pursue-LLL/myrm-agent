'use client';

/**
 * [INPUT]
 * - @/lib/utils/classnameUtils::cn (POS: Tailwind class merge helper)
 * - next-intl::useTranslations (POS: i18n; `chat.newTaskCard.mode*` labels)
 *
 * [OUTPUT]
 * - WorkModeTabs: Segmented control for the three work modes (Local Workspace / Cloud Sandbox / Quick Chat)
 * - NewTaskMode: Union of the three work modes
 *
 * [POS]
 * Presentational mode switcher of NewTaskWorkContextCard. Phones render three equal cells with the icon above the
 * label so every mode stays visible in any locale; from `sm` up it is a single flex row. It keeps no state: the card
 * owns what switching a mode means for the chat store.
 */

import React, { memo } from 'react';
import { useTranslations } from 'next-intl';
import { Boxes, HardDrive, MessageSquare, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

export type NewTaskMode = 'local' | 'cloud' | 'chat';

interface ModeTab {
  mode: NewTaskMode;
  Icon: LucideIcon;
  iconClass: string;
  labelKey: 'modeLocal' | 'modeCloud' | 'modeChat';
}

const MODE_TABS: readonly ModeTab[] = [
  { mode: 'local', Icon: HardDrive, iconClass: 'text-primary', labelKey: 'modeLocal' },
  { mode: 'cloud', Icon: Boxes, iconClass: 'text-blue-500', labelKey: 'modeCloud' },
  { mode: 'chat', Icon: MessageSquare, iconClass: 'text-emerald-500', labelKey: 'modeChat' },
];

// Below sm each mode is a narrow cell: the label wraps on word boundaries and, when one word is still wider than the
// cell, hyphenates by the document language (`DocumentLang` keeps `<html lang>` on the active locale) instead of
// being cut off or breaking mid-word.
const MODE_LABEL_CLASS = 'max-w-full text-balance hyphens-auto break-words text-center leading-tight sm:text-left';

interface WorkModeTabsProps {
  value: NewTaskMode;
  onChange: (mode: NewTaskMode) => void;
}

export const WorkModeTabs = memo(function WorkModeTabs({ value, onChange }: WorkModeTabsProps) {
  const t = useTranslations('chat.newTaskCard');

  return (
    <div className="grid w-full grid-cols-3 gap-1.5 p-1 rounded-xl bg-muted/50 text-xs font-medium sm:flex sm:w-auto sm:items-center">
      {MODE_TABS.map(({ mode, Icon, iconClass, labelKey }) => (
        <button
          key={mode}
          type="button"
          data-testid={`context-mode-${mode}`}
          onClick={() => onChange(mode)}
          className={cn(
            'flex min-w-0 flex-col items-center justify-center gap-1 px-2 py-2 sm:flex-row sm:gap-1.5 sm:px-3 sm:py-1.5 rounded-lg transition-all',
            value === mode
              ? 'bg-background text-foreground shadow-xs font-semibold'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          <Icon className={cn('h-3.5 w-3.5', iconClass)} />
          <span className={MODE_LABEL_CLASS}>{t(labelKey)}</span>
        </button>
      ))}
    </div>
  );
});
