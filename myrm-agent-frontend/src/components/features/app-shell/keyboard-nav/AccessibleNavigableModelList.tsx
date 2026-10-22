'use client';

/**
 * 无障碍全键盘导航模型列表组件
 *
 * 规范遵循 WAI-ARIA Listbox 范式，提供 ArrowUp/Down 高亮游标、Enter 确认及滚动对齐。
 */

/* oxlint-disable jsx-a11y/prefer-tag-over-role */
import React, { useRef } from 'react';
import { Cpu, Check, CornerDownLeft, Sparkles, AlertCircle } from 'lucide-react';
import type { NavigableModelItem } from './modelPickerKeyboardTypes';
import { useModelPickerKeyboardNav } from './useModelPickerKeyboardNav';
import { formatAriaActiveDescendantId } from './modelPickerKeyboardEngine';

export interface AccessibleNavigableModelListProps {
  items: NavigableModelItem[];
  selectedId?: string;
  isOpen?: boolean;
  onSelect?: (item: NavigableModelItem) => void;
  onClose?: () => void;
  className?: string;
}

export const AccessibleNavigableModelList: React.FC<AccessibleNavigableModelListProps> = ({
  items,
  selectedId,
  isOpen = true,
  onSelect,
  onClose,
  className = '',
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);

  const { activeIndex, handleKeyDown } = useModelPickerKeyboardNav({
    items,
    isOpen,
    onSelect,
    onClose,
    containerRef,
  });

  const activeDescendantId = formatAriaActiveDescendantId('model-opt', activeIndex, items);

  return (
    <div
      className={`flex flex-col bg-popover text-popover-foreground border border-border rounded-xl shadow-lg overflow-hidden ${className}`}
      data-testid="accessible-navigable-model-list"
    >
      <div
        ref={containerRef}
        role="listbox"
        tabIndex={0}
        aria-activedescendant={activeDescendantId}
        onKeyDown={handleKeyDown}
        className="max-h-72 overflow-y-auto p-1.5 space-y-1 focus:outline-none focus:ring-1 focus:ring-primary/40 rounded-t-xl"
        data-testid="navigable-model-listbox"
      >
        {items.length === 0 ? (
          <div className="py-6 text-center text-xs text-muted-foreground">暂无匹配的模型项</div>
        ) : (
          items.map((item, index) => {
            const isHighlighted = index === activeIndex;
            const isSelected = item.id === selectedId;
            const optionId = `model-opt-${item.id}`;

            return (
              <div
                key={item.id}
                id={optionId}
                role="option"
                tabIndex={-1}
                aria-selected={isSelected}
                aria-disabled={item.disabled}
                data-nav-index={index}
                data-testid={`model-nav-item-${item.id}`}
                onClick={() => {
                  if (!item.disabled) {
                    onSelect?.(item);
                  }
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    if (!item.disabled) {
                      onSelect?.(item);
                    }
                  }
                }}
                className={`flex items-center justify-between px-3 py-2 rounded-lg text-xs cursor-pointer transition-colors ${
                  item.disabled
                    ? 'opacity-40 cursor-not-allowed'
                    : isHighlighted
                      ? 'bg-accent text-accent-foreground font-medium'
                      : isSelected
                        ? 'bg-primary/10 text-primary'
                        : 'hover:bg-muted/60 text-foreground'
                }`}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <div
                    className={`w-6 h-6 rounded-md flex items-center justify-center shrink-0 ${
                      item.isSmartRouting
                        ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
                        : item.isMoaPreset
                          ? 'bg-purple-500/15 text-purple-600 dark:text-purple-400'
                          : 'bg-muted text-muted-foreground'
                    }`}
                  >
                    {item.isSmartRouting ? (
                      <Sparkles className="w-3.5 h-3.5" />
                    ) : item.disabled ? (
                      <AlertCircle className="w-3.5 h-3.5" />
                    ) : (
                      <Cpu className="w-3.5 h-3.5" />
                    )}
                  </div>

                  <div className="min-w-0 text-left">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="font-medium truncate">{item.label}</span>
                      {item.badge && (
                        <span className="text-[10px] px-1.5 py-0.2 rounded bg-muted/80 text-muted-foreground font-mono">
                          {item.badge}
                        </span>
                      )}
                    </div>
                    {item.description && (
                      <p className="text-[11px] text-muted-foreground truncate">{item.description}</p>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-1.5 shrink-0 ml-2">
                  {isSelected && <Check className="w-3.5 h-3.5 text-primary" />}
                  {isHighlighted && !item.disabled && (
                    <span className="text-[10px] text-muted-foreground px-1 py-0.5 rounded bg-muted flex items-center gap-0.5">
                      <CornerDownLeft className="w-2.5 h-2.5" />
                      <span>选择</span>
                    </span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      <div className="px-3 py-2 border-t border-border/60 bg-muted/30 text-[11px] text-muted-foreground flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span>
            <kbd className="px-1 py-0.5 bg-background border border-border rounded text-[10px]">↑</kbd>
            <kbd className="px-1 py-0.5 bg-background border border-border rounded text-[10px] ml-0.5">↓</kbd> 漫游
          </span>
          <span>
            <kbd className="px-1 py-0.5 bg-background border border-border rounded text-[10px]">↵</kbd> 确认
          </span>
        </div>
        <span>
          <kbd className="px-1 py-0.5 bg-background border border-border rounded text-[10px]">Esc</kbd> 关闭
        </span>
      </div>
    </div>
  );
};
