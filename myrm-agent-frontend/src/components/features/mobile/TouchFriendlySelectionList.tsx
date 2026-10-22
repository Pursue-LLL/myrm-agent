'use client';

/**
 * [INPUT]
 * - mobileCockpitTypes: TouchFriendlySelectionListProps, TouchOptionItem, TouchSelectionMode
 * - lucide-react icons
 * - next-intl: useTranslations
 *
 * [OUTPUT]
 * - TouchFriendlySelectionList: Mobile Touch-Optimized TUI/CLI Selection List
 *
 * [POS]
 * Mobile Remote Companion touch target adapter for single/multiple option selection without arrow keys.
 */

import React, { useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Check, Circle, CheckSquare, Square, CheckCircle2 } from 'lucide-react';
import {
  TouchFriendlySelectionListProps,
  TouchOptionItem,
} from './mobileCockpitTypes';

export const TouchFriendlySelectionList: React.FC<TouchFriendlySelectionListProps> = ({
  options,
  mode = 'single',
  selectedIds,
  onChange,
  onConfirm,
  title,
  className = '',
}) => {
  let t = (key: string, values?: Record<string, string | number>): string => {
    if (key === 'selectedCount' && values?.count !== undefined) {
      return `已选 ${values.count} 项`;
    }
    return key;
  };
  try {
    const translation = useTranslations('mobileCockpit.selectionList');
    t = (key: string, values?: Record<string, string | number>): string =>
      translation(key, values);
  } catch {
    // Fallback in tests
  }

  const handleToggle = useCallback(
    (option: TouchOptionItem) => {
      if (option.disabled) {
        return;
      }

      if (mode === 'single') {
        onChange([option.id]);
        return;
      }

      const isAlreadySelected = selectedIds.includes(option.id);
      if (isAlreadySelected) {
        onChange(selectedIds.filter((id) => id !== option.id));
      } else {
        onChange([...selectedIds, option.id]);
      }
    },
    [mode, selectedIds, onChange],
  );

  const handleConfirm = useCallback(() => {
    if (onConfirm) {
      onConfirm(selectedIds);
    }
  }, [onConfirm, selectedIds]);

  const handleReset = useCallback(() => {
    onChange([]);
  }, [onChange]);

  return (
    <div
      data-testid="touch-friendly-selection-list"
      className={`rounded-3xl border border-border/80 bg-card/95 p-4 shadow-xl backdrop-blur-md ${className}`}
    >
      <div className="flex items-center justify-between pb-3 border-b border-border/50">
        <div>
          <h4 className="text-sm font-bold text-foreground">
            {title || t('title')}
          </h4>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            {mode === 'single' ? t('singleSelectHint') : t('multiSelectHint')}
          </p>
        </div>

        {mode === 'multiple' && selectedIds.length > 0 ? (
          <button
            type="button"
            onClick={handleReset}
            className="text-[11px] font-medium text-muted-foreground hover:text-foreground underline decoration-dotted"
          >
            {t('clearAll')}
          </button>
        ) : null}
      </div>

      <div className="my-3 space-y-2 max-h-80 overflow-y-auto pr-0.5">
        {options.map((option, index) => {
          const isSelected = selectedIds.includes(option.id);
          const isDisabled = Boolean(option.disabled);

          return (
            <button
              key={option.id}
              type="button"
              disabled={isDisabled}
              data-testid={`touch-option-${option.id}`}
              onClick={() => {
                handleToggle(option);
              }}
              className={`w-full flex items-start gap-3 rounded-2xl border p-3.5 text-left transition-all active:scale-[0.98] ${
                isSelected
                  ? 'border-primary/80 bg-primary/10 shadow-sm'
                  : 'border-border/70 bg-background/80 hover:bg-muted/40'
              } ${isDisabled ? 'opacity-40 cursor-not-allowed' : ''}`}
            >
              <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg text-primary">
                {mode === 'single' ? (
                  isSelected ? (
                    <CheckCircle2 className="h-5 w-5 fill-primary text-primary-foreground" />
                  ) : (
                    <Circle className="h-5 w-5 text-muted-foreground/60" />
                  )
                ) : isSelected ? (
                  <CheckSquare className="h-5 w-5 fill-primary text-primary-foreground" />
                ) : (
                  <Square className="h-5 w-5 text-muted-foreground/60" />
                )}
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  {option.shortcut ? (
                    <span className="inline-flex h-4 items-center rounded bg-muted px-1.5 font-mono text-[10px] font-bold text-muted-foreground">
                      {option.shortcut}
                    </span>
                  ) : (
                    <span className="inline-flex h-4 items-center rounded bg-muted/60 px-1 font-mono text-[10px] text-muted-foreground">
                      {index + 1}
                    </span>
                  )}
                  <span
                    className={`text-xs font-semibold truncate ${
                      isSelected ? 'text-primary' : 'text-foreground'
                    }`}
                  >
                    {option.label}
                  </span>
                  {option.badge ? (
                    <span className="ml-auto rounded-full bg-secondary/80 px-2 py-0.5 text-[10px] font-medium text-secondary-foreground">
                      {option.badge}
                    </span>
                  ) : null}
                </div>

                {option.description ? (
                  <p className="mt-1 text-[11px] text-muted-foreground line-clamp-2">
                    {option.description}
                  </p>
                ) : null}
              </div>
            </button>
          );
        })}
      </div>

      {mode === 'multiple' ? (
        <div className="pt-2 border-t border-border/50">
          <button
            type="button"
            data-testid="selection-confirm-btn"
            onClick={handleConfirm}
            disabled={selectedIds.length === 0}
            className="flex h-12 w-full items-center justify-center gap-2 rounded-2xl bg-primary text-xs font-bold text-primary-foreground shadow-md hover:bg-primary/90 active:scale-95 transition-all disabled:opacity-40"
          >
            <Check className="h-4 w-4" />
            <span>
              {t('confirmSelection')} (
              {t('selectedCount', { count: selectedIds.length })})
            </span>
          </button>
        </div>
      ) : null}
    </div>
  );
};
