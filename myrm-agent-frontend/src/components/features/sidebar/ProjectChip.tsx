'use client';

/**
 * [INPUT]
 * - @/theme-engine::resolveContrastSafeForeground (POS: 在项目色底上取可读的文字色)
 *
 * [OUTPUT]
 * - ProjectChip: 「全部」「未归类」与各项目的过滤芯片
 * - ProjectChipInput: 新建与重命名共用的行内名称输入框
 *
 * [POS]
 * ProjectBar 的芯片原语，只管尺寸与可读性，状态和交互由 ProjectBar 持有。
 * 点击目标：指针设备 24px（WCAG 2.5.8），手机 40px；文字桌面 11px、手机 12px，手机输入框 16px 以免 iOS 聚焦时缩放页面；
 * 选中的项目芯片按项目色取字色（项目色多为浅色，白字只有 1.3 到 2.8:1）；名称过长时截断，不撑出侧栏。
 */
import type { CSSProperties, MouseEvent, Ref } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { resolveContrastSafeForeground } from '@/theme-engine';

/** 选中芯片的填充：项目色配按对比度选出的字色；没有项目色时用强调色，字色由 `text-[var(--accent-warm-foreground)]` 给。 */
const selectedFill = (color?: string): CSSProperties =>
  color
    ? { backgroundColor: color, borderColor: color, color: resolveContrastSafeForeground(color) }
    : { backgroundColor: 'var(--accent-warm)', borderColor: 'var(--accent-warm)' };

interface ProjectChipProps {
  active: boolean;
  isMobile: boolean;
  /** 项目色；「全部」「未归类」没有项目色，选中时用强调色。 */
  color?: string;
  onClick: () => void;
  onContextMenu?: (event: MouseEvent) => void;
  /** 同时作为悬停提示，名称被截断时仍能读到全名。 */
  children: string;
}

export function ProjectChip({ active, isMobile, color, onClick, onContextMenu, children }: ProjectChipProps) {
  return (
    <button
      onClick={onClick}
      onContextMenu={onContextMenu}
      aria-pressed={active}
      title={children}
      className={cn(
        'max-w-full truncate rounded-full border border-transparent font-medium transition-all select-none',
        isMobile ? 'h-10 px-3.5 text-xs' : 'h-6 px-2.5 text-[11px]',
        active
          ? !color && 'text-[var(--accent-warm-foreground)]'
          : 'bg-black/4 text-muted-foreground hover:bg-black/8 hover:text-foreground dark:bg-white/6 dark:hover:bg-white/10',
      )}
      style={active ? selectedFill(color) : undefined}
    >
      {color && !active && (
        <span className="inline-block w-1.5 h-1.5 rounded-full mr-1 align-middle" style={{ backgroundColor: color }} />
      )}
      {children}
    </button>
  );
}

interface ProjectChipInputProps {
  inputRef: Ref<HTMLInputElement>;
  value: string;
  isMobile: boolean;
  placeholder?: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
}

export function ProjectChipInput({
  inputRef,
  value,
  isMobile,
  placeholder,
  onChange,
  onSubmit,
  onCancel,
}: ProjectChipInputProps) {
  return (
    <input
      ref={inputRef}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      onBlur={onSubmit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          onSubmit();
        }
        if (e.key === 'Escape') {
          onCancel();
        }
      }}
      className={cn(
        'min-w-0 max-w-full rounded-full border border-primary/30 bg-transparent px-2.5 outline-none placeholder:text-muted-foreground',
        isMobile ? 'h-10 w-36 text-base' : 'h-6 w-24 text-[11px]',
      )}
    />
  );
}
