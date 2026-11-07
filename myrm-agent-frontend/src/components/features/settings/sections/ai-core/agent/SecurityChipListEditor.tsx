'use client';

/**
 * [INPUT] ./useSecurityListEditors::ListEditorBinding (POS: 列表项、输入框与增删动作)
 * [OUTPUT] SecurityChipListEditor: 安全策略的字符串列表卡片（标题 + 芯片列表 + 输入添加行 + 错误 / 空状态提示），可附加子内容
 * [POS] AgentSecurityTab 的允许路径、域名白名单、域名黑名单与命令拒绝列表共用的编辑卡片。
 */

import type { ReactNode } from 'react';
import { IconPlus, IconX } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import type { ListEditorBinding } from './useSecurityListEditors';

type ChipTone = 'primary' | 'success' | 'danger';

const CHIP_TONES: Record<ChipTone, { chip: string; code: string; remove: string }> = {
  primary: { chip: 'bg-primary/10 border border-primary/30', code: 'text-primary', remove: 'text-primary/60' },
  success: {
    chip: 'bg-emerald-500/10 border border-emerald-500/30',
    code: 'text-emerald-700 dark:text-emerald-400',
    remove: 'text-emerald-500/60',
  },
  danger: {
    chip: 'bg-destructive/10 border border-destructive/30',
    code: 'text-destructive-text',
    remove: 'text-destructive-text/60',
  },
};

interface SecurityChipListEditorProps extends ListEditorBinding {
  /** Marks the card as a scroll target of the health-score fixes; the highlight ring fades in on it. */
  scrollTargetId?: string;
  icon: ReactNode;
  title: string;
  description: string;
  tone: ChipTone;
  /** Leading icon inside every chip. */
  chipIcon?: ReactNode;
  placeholder: string;
  addLabel: string;
  emptyText: string;
  monospaceInput?: boolean;
  /** Stacks the input above the add button on narrow screens. */
  stackOnMobile?: boolean;
  children?: ReactNode;
}

export function SecurityChipListEditor({
  scrollTargetId,
  icon,
  title,
  description,
  tone,
  chipIcon,
  items,
  value,
  onValueChange,
  onAdd,
  onRemove,
  error,
  placeholder,
  addLabel,
  emptyText,
  monospaceInput,
  stackOnMobile,
  children,
}: SecurityChipListEditorProps) {
  const toneClasses = CHIP_TONES[tone];

  return (
    <div
      id={scrollTargetId}
      className={cn(
        'rounded-xl border border-border bg-card p-4 space-y-3',
        scrollTargetId && 'transition-all duration-300',
      )}
    >
      <div>
        <h3 className="text-sm font-medium text-foreground flex items-center gap-1.5">
          {icon}
          {title}
        </h3>
        <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
      </div>

      {items.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {items.map((item, idx) => (
            <div
              key={`${item}-${idx}`}
              className={cn('flex items-center gap-1.5 px-2.5 py-1 rounded-full', toneClasses.chip)}
            >
              {chipIcon}
              <code className={cn('text-xs font-mono', toneClasses.code)}>{item}</code>
              <button
                type="button"
                onClick={() => onRemove(idx)}
                className={cn(toneClasses.remove, 'hover:text-destructive-text transition-colors')}
              >
                <IconX className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      <div
        className={cn(stackOnMobile ? 'flex flex-col gap-2 sm:flex-row sm:items-center' : 'flex items-center gap-2')}
      >
        <Input
          placeholder={placeholder}
          value={value}
          onChange={(e) => onValueChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              onAdd();
            }
          }}
          className={cn('flex-1 text-sm', monospaceInput && 'font-mono')}
        />
        <Button variant="outline" size="sm" onClick={onAdd} disabled={!value.trim()}>
          <IconPlus className="h-4 w-4 mr-1" />
          {addLabel}
        </Button>
      </div>

      {error && <p className="text-xs text-destructive-text">{error}</p>}

      {items.length === 0 && !error && <p className="text-xs text-muted-foreground/70 italic">{emptyText}</p>}

      {children}
    </div>
  );
}
