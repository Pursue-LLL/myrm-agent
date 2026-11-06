'use client';

/**
 * [INPUT]
 * - react-textarea-autosize (POS: 随内容增高的文本框)
 * - @/hooks/chat/useChatTurnPrewarm::useChatTurnPrewarm (POS: 聚焦时预热下一轮的执行单元)
 * - @/hooks/message-input/messageInputKeyRouter::{resolveBusySubmitMode, resolveBusyPlaceholderKey} (POS: 运行中提交的落点与提示文案)
 * - @/lib/utils/textEntry::isTextEntry (POS: 用户是否正在别的输入控件里打字)
 * - @/services/memory::reportUserActivity (POS: 用户活动上报)
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线，会话与 Agent 配置)
 *
 * [OUTPUT]
 * - ComposerTextarea: 聊天输入框的文本区域。
 *
 * [POS]
 * 文本区域与它的副作用：输入时节流上报「正在输入」；聚焦时预热下一轮，失焦且焦点不再停在输入区内时取消预热；
 * 占位提示按「运行中 / 全屏编辑 / 输入历史预览」切换，运行中的提示说明回车实际会做什么。
 * 空会话首屏传 `focusOnMount`：在带键盘的桌面上挂载即把光标放进来（不滚动页面、不抢别处正在输入的控件）；
 * 这时的焦点不是用户给的，所以在用户碰它（按下、按键、输入）之前，失焦不取消预热，
 * 否则点一下示例 prompt 卡片就会放掉空会话挂载时启动的预热，随后的发送变成冷启动。
 */
import { type ChangeEventHandler, type ClipboardEventHandler, type RefObject, useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';
import TextareaAutosize from 'react-textarea-autosize';

import { useChatTurnPrewarm } from '@/hooks/chat/useChatTurnPrewarm';
import { resolveBusyPlaceholderKey, resolveBusySubmitMode } from '@/hooks/message-input/messageInputKeyRouter';
import { cn } from '@/lib/utils/classnameUtils';
import { isTextEntry } from '@/lib/utils/textEntry';
import { reportUserActivity } from '@/services/memory';
import useChatStore from '@/store/useChatStore';

/** Typing is reported at most this often, across every composer on the page. */
const TYPING_REPORT_INTERVAL_MS = 5000;
/** Focus may hop to another control inside the composer; wait this long before treating a blur as leaving it. */
const BLUR_SETTLE_MS = 120;
/** The desktop layout with a mouse or trackpad: a keyboard is at hand, and focusing raises no on-screen keyboard. */
const FOCUS_ON_MOUNT_QUERY = '(min-width: 640px) and (pointer: fine)';

function canFocusOnMount(): boolean {
  return (
    typeof window.matchMedia === 'function' &&
    window.matchMedia(FOCUS_ON_MOUNT_QUERY).matches &&
    !isTextEntry(document.activeElement)
  );
}

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
  /** Put the cursor here on mount, where a keyboard is at hand. */
  focusOnMount?: boolean;
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
  focusOnMount = false,
  onChange,
  onPaste,
  onCaretMove,
}: ComposerTextareaProps) {
  const chatT = useTranslations('chat');
  const chatId = useChatStore((s) => s.chatId);
  const busyInputMode = useChatStore((s) => s.agentConfig?.busyInputMode);
  const { triggerPrewarm, cancelPrewarm, shouldPrewarm } = useChatTurnPrewarm();

  // False while the cursor is here only because of `focusOnMount`, until the viewer first touches the text area.
  const engaged = useRef(true);
  const markEngaged = () => {
    engaged.current = true;
  };

  useEffect(() => {
    if (!focusOnMount || !canFocusOnMount()) {
      return;
    }
    engaged.current = false;
    inputRef.current?.focus({ preventScroll: true });
  }, [focusOnMount, inputRef]);

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
        if (!engaged.current) {
          return;
        }
        window.setTimeout(() => {
          const active = document.activeElement;
          if (active instanceof HTMLElement && active.closest('[data-chat-composer]')) {
            return;
          }
          void cancelPrewarm();
        }, BLUR_SETTLE_MS);
      }}
      onPointerDown={markEngaged}
      onKeyDown={markEngaged}
      onChange={(e) => {
        markEngaged();
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
