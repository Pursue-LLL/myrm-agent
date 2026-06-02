'use client';

/**
 * CLI Agent 模式选择器
 *
 * 在现有的 SearchModeSelector 旁边显示，用于切换到 Claude Code 模式。
 * 已整合到现有架构，通过 actionMode='claude_code' 使用。
 */

import { useTranslations } from 'next-intl';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils/classnameUtils';
import type { ActionMode } from '@/store/chat/types';
import { IconTerminal, IconChevronDown, IconGlow } from '@/components/ui/icons/PremiumIcons';

interface CLIAgentSelectorProps {
  actionMode: ActionMode;
  setActionMode: (mode: ActionMode) => void;
  className?: string;
}

/**
 * CLI Agent 下拉选择器
 *
 * 当用户选择 Claude Code 时，actionMode 会变为 'claude_code'，
 * 消息发送会自动路由到 CLI Agent。
 */
export function CLIAgentSelector({ actionMode, setActionMode, className }: CLIAgentSelectorProps) {
  const t = useTranslations('cliAgent');

  const isCLIMode = actionMode === 'claude_code';

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant={isCLIMode ? 'secondary' : 'ghost'}
          size="sm"
          className={cn('flex items-center gap-1.5', isCLIMode && 'bg-primary/10 text-primary', className)}
        >
          <IconTerminal className="h-4 w-4" />
          {isCLIMode && <span className="text-xs">Claude Code</span>}
          <IconChevronDown className="h-3 w-3" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        <DropdownMenuItem onClick={() => setActionMode('agent')} className={cn(actionMode === 'agent' && 'bg-accent')}>
          <IconGlow className="mr-2 h-4 w-4 opacity-70" />
          {t('modeAgent') || 'AI Agent'}
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => setActionMode('claude_code')}
          className={cn(actionMode === 'claude_code' && 'bg-accent')}
        >
          <IconTerminal className="mr-2 h-4 w-4 opacity-70" />
          Claude Code
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * CLI Agent 状态徽章
 *
 * 显示当前是否处于 Claude Code 模式
 */
export function CLIAgentBadge({ actionMode }: { actionMode: ActionMode }) {
  if (actionMode !== 'claude_code') return null;

  return (
    <div className="flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-1 text-xs text-primary">
      <IconTerminal className="h-3 w-3" />
      <span>Claude Code</span>
    </div>
  );
}
