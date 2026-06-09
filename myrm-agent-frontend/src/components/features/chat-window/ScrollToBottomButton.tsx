/**
 * 滚动到底部按钮
 *
 * [INPUT]
 * - hasNewMessage: boolean (POS: 是否有新的 agent 消息在视口下方)
 * - visible: boolean (POS: 用户是否已滚离底部)
 * - onClick: () => void (POS: 点击回调，执行 scrollToBottom)
 *
 * [OUTPUT]
 * - ScrollToBottomButton: 固定在聊天区域右下角的浮动按钮
 *   - 默认态：圆形 ↓ 箭头
 *   - 新消息态：药丸形「New message ↓」，带强调色
 *
 * [POS]
 * 聊天窗口的滚动辅助按钮。当用户向上滚动时显示，
 * 点击后平滑滚动回最新消息。当有新消息产生时，
 * 从箭头态变为药丸态，提供视觉提示。
 */

'use client';

import { memo } from 'react';
import { ArrowDown } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';

interface ScrollToBottomButtonProps {
  visible: boolean;
  hasNewMessage: boolean;
  onClick: () => void;
}

const ScrollToBottomButton = memo<ScrollToBottomButtonProps>(({ visible, hasNewMessage, onClick }) => {
  const t = useTranslations('chat.scrollCue');

  if (!visible) return null;

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={hasNewMessage ? t('newMessage') : t('scrollToBottom')}
      className={cn(
        'fixed z-40 flex items-center justify-center',
        'shadow-md border cursor-pointer',
        'transition-all duration-200 ease-out',
        'hover:scale-105 active:scale-95',
        hasNewMessage
          ? [
              'right-4 md:right-6 bottom-44 md:bottom-48',
              'h-8 px-3 gap-1.5 rounded-full',
              'bg-primary text-primary-foreground',
              'border-primary/50',
              'animate-in fade-in slide-in-from-bottom-2',
            ]
          : [
              'right-4 md:right-6 bottom-44 md:bottom-48',
              'h-9 w-9 rounded-full',
              'bg-background/90 backdrop-blur-sm text-muted-foreground',
              'border-border',
              'hover:text-foreground hover:border-foreground/20',
            ],
      )}
    >
      {hasNewMessage && (
        <span className="text-xs font-medium whitespace-nowrap">{t('newMessage')}</span>
      )}
      <ArrowDown className={cn('shrink-0', hasNewMessage ? 'h-3.5 w-3.5' : 'h-4 w-4')} />
    </button>
  );
});

ScrollToBottomButton.displayName = 'ScrollToBottomButton';

export default ScrollToBottomButton;
