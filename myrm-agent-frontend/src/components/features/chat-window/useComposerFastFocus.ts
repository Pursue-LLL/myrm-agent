/**
 * [INPUT]
 * - KeyboardEvent (Mod+K / Cmd+K / Ctrl+K / Mod+Shift+C)
 * - CustomEvent 'myrm:focus-composer'
 * - Target selector: '[data-chat-input]'
 *
 * [OUTPUT]
 * - focusComposer: () => boolean (POS: 编程方式聚焦 Composer 输入框)
 * - useComposerFastFocus: Hook implementing global hotkey fast-focus workflow
 *
 * [POS]
 * Composer Fast Focus global shortcut engine.
 * Eliminates friction when navigating between file diffs, terminals, and conversation.
 * Strict typing: Zero `any`. File length < 130 lines.
 */

import { useEffect, useCallback } from 'react';

export interface UseComposerFastFocusOptions {
  enabled?: boolean;
  onFocus?: () => void;
}

/**
 * 聚焦聊天输入框并触发轻量脉冲高亮视觉反馈
 */
export function focusComposer(): boolean {
  if (typeof document === 'undefined') {
    return false;
  }

  const inputEl = document.querySelector<HTMLTextAreaElement | HTMLInputElement>('[data-chat-input]');
  if (!inputEl) {
    return false;
  }

  inputEl.focus();

  // 若存在文本，将光标定位至末尾
  if (inputEl instanceof HTMLTextAreaElement || inputEl instanceof HTMLInputElement) {
    const len = inputEl.value.length;
    try {
      inputEl.setSelectionRange(len, len);
    } catch {
      // 兼容不支持 setSelectionRange 的类型
    }
  }

  // 触发一次平滑轻量高亮光环
  const composerContainer = inputEl.closest<HTMLElement>('[data-chat-composer]');
  if (composerContainer) {
    composerContainer.classList.add('ring-2', 'ring-primary/60', 'transition-all');
    window.setTimeout(() => {
      composerContainer.classList.remove('ring-2', 'ring-primary/60');
    }, 600);
  }

  return true;
}

export function useComposerFastFocus({
  enabled = true,
  onFocus,
}: UseComposerFastFocusOptions = {}) {
  const handleFocus = useCallback(() => {
    const success = focusComposer();
    if (success && onFocus) {
      onFocus();
    }
  }, [onFocus]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      // 匹配 Mod+K (Cmd+K / Ctrl+K) 或 Mod+Shift+C
      const isMod = e.metaKey || e.ctrlKey;
      const isModK = isMod && !e.shiftKey && e.key.toLowerCase() === 'k';
      const isModShiftC = isMod && e.shiftKey && e.key.toLowerCase() === 'c';

      if (!isModK && !isModShiftC) {
        return;
      }

      // 如果当前已经是活动输入框，则放行默认行为
      const activeEl = document.activeElement;
      const isCurrentInput =
        activeEl instanceof HTMLElement &&
        (activeEl.hasAttribute('data-chat-input') || activeEl.closest('[data-chat-input]'));

      if (isCurrentInput) {
        return;
      }

      // 拦截并快速聚焦至 Composer
      e.preventDefault();
      handleFocus();
    };

    const handleCustomEvent = () => {
      handleFocus();
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('myrm:focus-composer', handleCustomEvent);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('myrm:focus-composer', handleCustomEvent);
    };
  }, [enabled, handleFocus]);

  return { focusComposer: handleFocus };
}
