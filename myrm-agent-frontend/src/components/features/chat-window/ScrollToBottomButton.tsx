/**
 * 滚动到底部按钮
 *
 * [INPUT]
 * - hasNewMessage: boolean (POS: 是否有新的 agent 消息在视口下方)
 * - visible: boolean (POS: 用户是否已滚离底部)
 * - onClick: () => void (POS: 点击回调，执行 scrollToBottom)
 * - pendingCount?: number (POS: 下方待读条目精确计数)
 * - pendingItems?: PendingCountCueItem[] (POS: 渐进微行披露)
 *
 * [OUTPUT]
 * - ScrollToBottomButton: 固定在聊天区域右下角的浮动按钮，支持待读数字徽标与多行渐进披露
 *
 * [POS]
 * 聊天窗口的滚动辅助按钮 (Item 43 P0)。
 * 严格控制在 130 行以内。零 `any`。
 */

'use client';

import { memo } from 'react';
import { ArrowDown } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { PendingCountCueItem } from './question-nav/userQuestionNavTypes';

interface ScrollToBottomButtonProps {
  visible: boolean;
  hasNewMessage: boolean;
  onClick: () => void;
  pendingCount?: number;
  pendingItems?: PendingCountCueItem[];
}

const ScrollToBottomButton = memo<ScrollToBottomButtonProps>(
  ({ visible, hasNewMessage, onClick, pendingCount = 0, pendingItems = [] }) => {
    const t = useTranslations('chat.scrollCue');

    if (!visible) {
      return null;
    }

    const showBadge = pendingCount > 0 || hasNewMessage;
    const countDisplay = pendingCount > 0 ? pendingCount : null;

    return (
      <div className="fixed right-4 md:right-6 bottom-44 md:bottom-48 z-40 flex flex-col items-end gap-1.5">
        {/* Exact Pending-Count Cue: 1-3 lines progressive disclosure */}
        {pendingItems.length > 0 && (
          <div className="flex flex-col gap-1 rounded-xl border border-border/80 bg-background/95 p-2 shadow-md backdrop-blur-sm text-[11px] max-w-56 animate-in fade-in slide-in-from-bottom-1">
            {pendingItems.slice(0, 3).map((item) => (
              <div key={item.messageId} className="flex items-center gap-1.5 truncate text-muted-foreground">
                <span className="font-semibold uppercase tracking-wider text-[10px] text-foreground/80">
                  {item.role}:
                </span>
                <span className="truncate">{item.snippet}</span>
              </div>
            ))}
            {pendingCount > 3 && (
              <div className="text-[10px] font-medium text-muted-foreground/75">
                +{pendingCount - 3} more
              </div>
            )}
          </div>
        )}

        <button
          type="button"
          onClick={onClick}
          aria-label={showBadge ? t('newMessage') : t('scrollToBottom')}
          className={cn(
            'flex items-center justify-center',
            'shadow-md border cursor-pointer',
            'transition-all duration-200 ease-out',
            'hover:scale-105 active:scale-95',
            showBadge
              ? [
                  'h-8 px-3 gap-1.5 rounded-full',
                  'bg-primary text-primary-foreground',
                  'border-primary/50',
                  'animate-in fade-in slide-in-from-bottom-2',
                ]
              : [
                  'h-9 w-9 rounded-full',
                  'bg-background/90 backdrop-blur-sm text-muted-foreground',
                  'border-border',
                  'hover:text-foreground hover:border-foreground/20',
                ],
          )}
        >
          {showBadge && (
            <span className="text-xs font-medium whitespace-nowrap">
              {countDisplay ? `${countDisplay} ${t('newMessage')}` : t('newMessage')}
            </span>
          )}
          <ArrowDown className={cn('shrink-0', showBadge ? 'h-3.5 w-3.5' : 'h-4 w-4')} />
        </button>
      </div>
    );
  },
);

ScrollToBottomButton.displayName = 'ScrollToBottomButton';

export default ScrollToBottomButton;
