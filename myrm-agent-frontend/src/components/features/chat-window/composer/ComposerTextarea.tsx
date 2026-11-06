'use client';

/**
 * [INPUT]
 * - react-textarea-autosize (POS: 随内容增高的文本框)
 * - @/hooks/chat/useChatTurnPrewarm::useChatTurnPrewarm (POS: 聚焦时预热下一轮的执行单元)
 * - @/hooks/message-input/messageInputKeyRouter::{resolveBusySubmitMode, resolveBusyPlaceholderKey} (POS: 运行中提交的落点与提示文案)
 * - @/services/memory::reportUserActivity (POS: 用户活动上报)
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线，会话与 Agent 配置)
 *
 * [OUTPUT]
 * - ComposerTextarea: 聊天输入框的文本区域。
 *
 * [POS]
 * 文本区域与它的三个副作用：输入时节流上报「正在输入」；聚焦时预热下一轮，失焦且焦点不再停在输入区内时取消预热；
 * 占位提示按「运行中 / 全屏编辑 / 输入历史预览」切换，运行中的提示说明回车实际会做什么。
 */
import type { ChangeEventHandler, ClipboardEventHandler, RefObject } from 'react';
import { useTranslations } from 'next-intl';
import TextareaAutosize from 'react-textarea-autosize';

import { useChatTurnPrewarm } from '@/hooks/chat/useChatTurnPrewarm';
import { resolveBusyPlaceholderKey, resolveBusySubmitMode } from '@/hooks/message-input/messageInputKeyRouter';
import { cn } from '@/lib/utils/classnameUtils';
import { reportUserActivity } from '@/services/memory';
import useChatStore from '@/store/useChatStore';

/** Typing is reported at most this often, across every composer on the page. */
const TYPING_REPORT_INTERVAL_MS = 5000;
/** Focus may hop to another control inside the composer; wait this long before treating a blur as leaving it. */
const BLUR_SETTLE_MS = 120;

let lastTypingReportTime = 0;
const reportTypingActivityThrottled = (chatId?: string) => {
  const now = Date.now();
  if (now - lastTypingReportTime > TYPING_REPORT_INTERVAL_MS) {
    lastTypingReportTime = now;
    void reportUserActivity(chatId, 'typing').catch(() => {});
  }
};

interface ComposerTextareaProps {
  inputRef: RefObject<HTMLTextAreaElement | null>;
  value: string;
  loading: boolean;
  hasFiles: boolean;
  /** The editor fills the screen: more rows, and the busy hint names the shortcut that sends there. */
  expanded: boolean;
  /** A history entry previewed in place of the placeholder. */
  ghostText?: string;
  onChange: ChangeEventHandler<HTMLTextAreaElement>;
  onPaste: ClipboardEventHandler<HTMLTextAreaElement>;
  /** The caret moved without the text changing (arrow keys, click). */
  onCaretMove: () => void;
}

export function ComposerTextarea({
  inputRef,
  value,
  loading,
  hasFiles,
  expanded,
  ghostText,
  onChange,
  onPaste,
  onCaretMove,
}: ComposerTextareaProps) {
  const chatT = useTranslations('chat');
  const chatId = useChatStore((s) => s.chatId);
  const busyInputMode = useChatStore((s) => s.agentConfig?.busyInputMode);
  const { triggerPrewarm, cancelPrewarm, shouldPrewarm } = useChatTurnPrewarm();

  // The busy hint names what Enter actually does, which depends on the agent's busy-input setting and attachments.
  const busyPlaceholderKey = resolveBusyPlaceholderKey(resolveBusySubmitMode(hasFiles, busyInputMode), expanded);
  const placeholder = ghostText
    ? ghostText
    : loading
      ? chatT(busyPlaceholderKey)
      : chatT(expanded ? 'input.expandedPlaceholder' : 'input.placeholder');

  return (
    <TextareaAutosize
      ref={inputRef}
      data-chat-input
      value={value}
      onFocus={() => {
        if (shouldPrewarm) {
          void triggerPrewarm();
        }
      }}
      onBlur={() => {
        window.setTimeout(() => {
          const active = document.activeElement;
          if (active instanceof HTMLElement && active.closest('[data-chat-composer]')) {
            return;
          }
          void cancelPrewarm();
        }, BLUR_SETTLE_MS);
      }}
      onChange={(e) => {
        onChange(e);
        reportTypingActivityThrottled(chatId);
      }}
      onPaste={onPaste}
      onKeyUp={onCaretMove}
      onClick={onCaretMove}
      minRows={expanded ? 8 : 2}
      className={cn(
        'bg-transparent placeholder:text-muted-foreground/50 text-base sm:text-sm text-black dark:text-white resize-none focus:outline-none w-full',
        expanded ? 'max-h-[75vh]' : 'max-h-24 sm:max-h-[35vh] lg:max-h-[40vh]',
      )}
      placeholder={placeholder}
    />
  );
}
