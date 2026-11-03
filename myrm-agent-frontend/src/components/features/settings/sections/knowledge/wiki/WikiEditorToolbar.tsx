'use client';

/**
 * [INPUT] lucide-react 矢量图标, cn 样式拼接工具, next-intl::useTranslations (POS: Internationalization hook)
 * [OUTPUT] WikiEditorToolbar: Wiki Markdown 格式快捷工具栏组件, ToolbarAction: 工具栏动作枚举
 * [POS] Wiki 编辑器子组件层。提供紧凑精巧的 Markdown 语法与 Wiki 双链快捷插入操作面板。
 */
import React, { memo } from 'react';
import { Bold, Italic, Heading2, Code, Quote, List, ListTodo, Link2, Table } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';

export type ToolbarAction = 'bold' | 'italic' | 'h2' | 'code' | 'quote' | 'bullet' | 'todo' | 'wikilink' | 'table';

interface WikiEditorToolbarProps {
  onAction: (action: ToolbarAction) => void;
  disabled?: boolean;
  className?: string;
}

interface ToolbarItem {
  id: ToolbarAction;
  icon: React.ComponentType<{ className?: string }>;
  hotkey?: string;
}

const TOOLBAR_ITEMS: ToolbarItem[] = [
  { id: 'bold', icon: Bold, hotkey: 'Ctrl+B' },
  { id: 'italic', icon: Italic, hotkey: 'Ctrl+I' },
  { id: 'h2', icon: Heading2 },
  { id: 'code', icon: Code },
  { id: 'quote', icon: Quote },
  { id: 'bullet', icon: List },
  { id: 'todo', icon: ListTodo },
  { id: 'wikilink', icon: Link2, hotkey: '[[' },
  { id: 'table', icon: Table },
];

export const WikiEditorToolbar: React.FC<WikiEditorToolbarProps> = memo(({ onAction, disabled = false, className }) => {
  const t = useTranslations('settings.wiki.toolbar');

  return (
    <div
      role="toolbar"
      aria-label={t('label')}
      className={cn(
        'flex items-center gap-0.5 px-2 py-1 border-b border-border bg-card/60 backdrop-blur-sm select-none overflow-x-auto',
        className,
      )}
    >
      {TOOLBAR_ITEMS.map((item) => {
        const Icon = item.icon;
        const isWikiLink = item.id === 'wikilink';
        const label = t(item.id);

        return (
          <button
            key={item.id}
            type="button"
            disabled={disabled}
            title={item.hotkey ? `${label} (${item.hotkey})` : label}
            onClick={(e) => {
              e.preventDefault();
              onAction(item.id);
            }}
            className={cn(
              'inline-flex items-center justify-center h-7 px-2 rounded text-xs font-medium transition-colors',
              'text-muted-foreground hover:text-foreground hover:bg-muted active:scale-95 disabled:pointer-events-none disabled:opacity-50',
              isWikiLink &&
                'text-primary font-semibold hover:text-primary hover:bg-primary/10 border border-primary/20',
            )}
          >
            <Icon className="w-3.5 h-3.5 mr-1 shrink-0" />
            <span className="hidden sm:inline">{label}</span>
          </button>
        );
      })}
    </div>
  );
});

WikiEditorToolbar.displayName = 'WikiEditorToolbar';
