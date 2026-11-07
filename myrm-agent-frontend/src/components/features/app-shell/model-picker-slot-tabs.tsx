'use client';

/**
 * [INPUT] ./model-picker-catalog::PickerModelSelection, SlotMode (POS: 选择器数据类型)
 * [OUTPUT] ModelSlotTabs: Primary / Fallback / Safety 槽位分段切换，Fallback 与 Safety 槽位带清除按钮
 * [POS] ModelPickerPopover 的槽位切换条，纯展示，当前槽位由父组件持有。
 */

import type { ReactNode } from 'react';
import { X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { PickerModelSelection, SlotMode } from './model-picker-catalog';

/** Inset ring keeps the keyboard focus indicator inside the track instead of overlapping neighbouring tabs. */
const SLOT_TAB_CLASS =
  'flex-1 px-3 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer select-none border-none outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring';

interface SlotTabButtonProps {
  slot: SlotMode;
  activeSlot: SlotMode;
  onSlotChange: (slot: SlotMode) => void;
  dotClass: string;
  label: string;
  children: ReactNode;
}

function SlotTabButton({ slot, activeSlot, onSlotChange, dotClass, label, children }: SlotTabButtonProps) {
  return (
    <button
      type="button"
      onClick={() => onSlotChange(slot)}
      className={cn(
        SLOT_TAB_CLASS,
        activeSlot === slot ? 'bg-background text-foreground' : 'text-muted-foreground hover:text-foreground',
      )}
    >
      <span className="flex items-center justify-center gap-1.5">
        <span className={cn('w-1.5 h-1.5 rounded-full', dotClass)} />
        {label}
        {children}
      </span>
    </button>
  );
}

interface ClearableSelectionProps {
  selection: PickerModelSelection | null | undefined;
  onClear: (() => void) | undefined;
}

function ClearableSelection({ selection, onClear }: ClearableSelectionProps) {
  const t = useTranslations('settings.defaultModel');

  if (!selection) {
    return <span className="text-[10px] text-muted-foreground/50">{t('notSet')}</span>;
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground truncate max-w-[80px]">
      {selection.model}
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onClear?.();
        }}
        className="p-0 hover:text-destructive-text transition-colors border-none bg-transparent"
      >
        <X size={8} />
      </button>
    </span>
  );
}

interface ModelSlotTabsProps {
  activeSlot: SlotMode;
  onSlotChange: (slot: SlotMode) => void;
  currentSelection: PickerModelSelection | null | undefined;
  fallbackSelection: PickerModelSelection | null | undefined;
  onClearFallback: (() => void) | undefined;
  hasSafetyFallbackSupport: boolean;
  safetyFallbackSelection: PickerModelSelection | null | undefined;
  onClearSafetyFallback: (() => void) | undefined;
}

export function ModelSlotTabs({
  activeSlot,
  onSlotChange,
  currentSelection,
  fallbackSelection,
  onClearFallback,
  hasSafetyFallbackSupport,
  safetyFallbackSelection,
  onClearSafetyFallback,
}: ModelSlotTabsProps) {
  const t = useTranslations('settings.defaultModel');

  return (
    <div className="px-2 pt-2 pb-1 border-b border-border">
      <div className="flex gap-1 p-0.5 rounded-lg bg-muted/60">
        <SlotTabButton
          slot="primary"
          activeSlot={activeSlot}
          onSlotChange={onSlotChange}
          dotClass="bg-primary"
          label={t('primaryModel')}
        >
          {currentSelection && (
            <span className="text-[10px] text-muted-foreground truncate max-w-[80px]">{currentSelection.model}</span>
          )}
        </SlotTabButton>
        <SlotTabButton
          slot="fallback"
          activeSlot={activeSlot}
          onSlotChange={onSlotChange}
          dotClass="bg-sky-500"
          label={t('fallbackSlot')}
        >
          <ClearableSelection selection={fallbackSelection} onClear={onClearFallback} />
        </SlotTabButton>
        {hasSafetyFallbackSupport && (
          <SlotTabButton
            slot="safety"
            activeSlot={activeSlot}
            onSlotChange={onSlotChange}
            dotClass="bg-emerald-500"
            label="Safety"
          >
            <ClearableSelection selection={safetyFallbackSelection} onClear={onClearSafetyFallback} />
          </SlotTabButton>
        )}
      </div>
    </div>
  );
}
