'use client';

/**
 * [INPUT]
 * - Lucide icons & standard class helpers
 * - React handlers for click, remove, keyboard navigation
 *
 * [OUTPUT]
 * - ContextChipItem: 渲染单项上下文胶囊（技能、模板、能力范围），提供语义色彩、精致图标、无障碍支持与触控热区。
 *
 * [POS]
 * 聊天输入区内联上下文胶囊条的基础原子项。遵循设计规范，严禁原生 Emoji，提供高质感微交互。
 */

import * as React from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

export type ContextChipVariant = 'skill' | 'template' | 'capability' | 'default';

export interface ContextChipItemProps {
  id: string;
  label: string;
  variant?: ContextChipVariant;
  icon?: React.ReactNode;
  subtitle?: string | null;
  onRemove?: () => void;
  onClick?: () => void;
  className?: string;
  disabled?: boolean;
  removeAriaLabel?: string;
}

const variantClasses: Record<ContextChipVariant, string> = {
  skill: 'border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300 hover:bg-sky-500/15',
  template: 'border-purple-500/30 bg-purple-500/10 text-purple-700 dark:text-purple-300 hover:bg-purple-500/15',
  capability: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/15',
  default: 'border-primary/20 bg-primary/10 text-primary hover:bg-primary/15',
};

export function ContextChipItem({
  id,
  label,
  variant = 'default',
  icon,
  subtitle,
  onRemove,
  onClick,
  className,
  disabled = false,
  removeAriaLabel = 'Remove',
}: ContextChipItemProps) {
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return;
    if (e.key === 'Delete' || e.key === 'Backspace') {
      if (onRemove) {
        e.preventDefault();
        onRemove();
      }
    } else if (e.key === 'Enter' || e.key === ' ') {
      if (onClick) {
        e.preventDefault();
        onClick();
      }
    }
  };

  return (
    <div
      data-testid={`context-chip-${id}`}
      tabIndex={onClick || onRemove ? 0 : undefined}
      onKeyDown={handleKeyDown}
      onClick={onClick}
      className={cn(
        'group inline-flex h-6.5 max-w-[260px] sm:max-w-[320px] items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium transition-all shadow-2xs select-none',
        variantClasses[variant],
        onClick && 'cursor-pointer hover:shadow-xs',
        disabled && 'opacity-50 pointer-events-none',
        className,
      )}
      title={subtitle ? `${label} (${subtitle})` : label}
    >
      {icon ? <span className="shrink-0 flex items-center justify-center opacity-80">{icon}</span> : null}
      <span className="truncate max-w-[160px] sm:max-w-[200px] leading-tight">{label}</span>
      {subtitle ? (
        <span className="hidden sm:inline-block max-w-[80px] truncate opacity-60 text-[10px] font-normal">
          {subtitle}
        </span>
      ) : null}
      {onRemove ? (
        <button
          type="button"
          data-testid={`context-chip-remove-${id}`}
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          disabled={disabled}
          className="shrink-0 -mr-1 ml-0.5 inline-flex h-5 w-5 items-center justify-center rounded-sm text-current opacity-60 transition-opacity hover:opacity-100 hover:bg-black/10 dark:hover:bg-white/10 focus:outline-hidden"
          aria-label={removeAriaLabel}
        >
          <X className="h-3 w-3" />
        </button>
      ) : null}
    </div>
  );
}
