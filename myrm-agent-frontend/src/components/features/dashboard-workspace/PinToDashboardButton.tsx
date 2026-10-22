/**
 * [INPUT] widgetId, title, language, content, sourceChatId
 * [OUTPUT] PinToDashboardButton (Compact action button for pinning widgets to dashboard)
 * [POS] Features -> Dashboard Workspace -> PinToDashboardButton
 */

'use client';

import React, { useCallback, useMemo } from 'react';
import { Pin, PinOff } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import { useDashboardWorkspaceStore } from './useDashboardWorkspaceStore';

export interface PinToDashboardButtonProps {
  widgetId: string;
  title?: string;
  language?: string;
  content: string;
  sourceChatId?: string;
  className?: string;
  showText?: boolean;
}

export const PinToDashboardButton: React.FC<PinToDashboardButtonProps> = ({
  widgetId,
  title = 'Interactive Widget',
  language = 'html',
  content,
  sourceChatId,
  className,
  showText = false,
}) => {
  const isPinned = useDashboardWorkspaceStore((state) =>
    state.widgets.some((w) => w.id === widgetId),
  );
  const togglePinWidget = useDashboardWorkspaceStore((state) => state.togglePinWidget);

  const handleToggle = useCallback(
    (e: React.MouseEvent<HTMLButtonElement>) => {
      e.stopPropagation();
      togglePinWidget({
        id: widgetId,
        title,
        language,
        content,
        sourceChatId,
      });
    },
    [togglePinWidget, widgetId, title, language, content, sourceChatId],
  );

  const tooltipText = useMemo(() => {
    if (isPinned) {
      return '已固定至工作台 (点击取消)';
    }
    return '固定到工作台 Dashboard';
  }, [isPinned]);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={handleToggle}
          className={cn(
            'inline-flex items-center gap-1.5 p-1 rounded-full transition-all duration-150',
            isPinned
              ? 'text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/40 hover:bg-amber-100 dark:hover:bg-amber-900/60'
              : 'text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800',
            className,
          )}
          aria-label={tooltipText}
          data-testid="pin-to-dashboard-btn"
        >
          {isPinned ? (
            <PinOff size={14} className="transition-transform active:scale-90" />
          ) : (
            <Pin size={14} className="transition-transform active:scale-90" />
          )}
          {showText ? (
            <span className="text-xs font-medium">
              {isPinned ? '已固定' : '固定'}
            </span>
          ) : null}
        </button>
      </TooltipTrigger>
      <TooltipContent side="top">{tooltipText}</TooltipContent>
    </Tooltip>
  );
};

PinToDashboardButton.displayName = 'PinToDashboardButton';
