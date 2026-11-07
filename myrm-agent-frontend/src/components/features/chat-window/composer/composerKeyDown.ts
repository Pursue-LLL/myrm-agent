/**
 * [INPUT]
 * - @/lib/utils/imeUtils::isImeComposing (POS: IME 组合输入判定)
 * - @/hooks/message-input/messageInputKeyRouter::resolveDualChannelAction (POS: 聊天输入框双通道键盘交互路由核心)
 * - @/hooks/message-input/useComposerContextChips::ContextChipItem (POS: 输入区上下文芯片)
 * - @/hooks/message-input/useInputHistory::useInputHistory (POS: 输入历史弹窗)
 *
 * [OUTPUT]
 * - handleComposerKeyDown: 输入区表单级按键分流。
 * - ComposerKeyDownContext: 分流所需的状态与动作。
 *
 * [POS]
 * 纯函数，不持有状态：每一路分流的依赖都由调用方传入，所以可以脱离组件逐路测试。
 * 分流顺序即优先级：IME 组合 > 退格删芯片 > 全屏编辑器开关 > 斜杠面板 > @ 面板 > 输入历史 > 回车提交 / 排队。
 */
import type { Dispatch, KeyboardEvent, SetStateAction } from 'react';

import { resolveDualChannelAction } from '@/hooks/message-input/messageInputKeyRouter';
import type { ContextChipItem } from '@/hooks/message-input/useComposerContextChips';
import type { useInputHistory } from '@/hooks/message-input/useInputHistory';
import { isImeComposing } from '@/lib/utils/imeUtils';

export interface ComposerKeyDownContext {
  inputMessage: string;
  setInputMessage: (text: string) => void;
  chips: readonly ContextChipItem[];
  loading: boolean;
  editorExpanded: boolean;
  setEditorExpanded: Dispatch<SetStateAction<boolean>>;
  showCommandPalette: boolean;
  onCommandKeyDown: (event: KeyboardEvent) => void;
  showReferenceMention: boolean;
  /** Returns true when the popover consumed the key. */
  onReferenceMentionKeyDown: (event: KeyboardEvent) => boolean;
  inputHistory: Pick<ReturnType<typeof useInputHistory>, 'popup' | 'handleKeyDown' | 'confirm'>;
  submit: () => void | Promise<void>;
  queue: () => void | Promise<void>;
}

export function handleComposerKeyDown(event: KeyboardEvent, ctx: ComposerKeyDownContext): void {
  // While an IME is composing, Enter confirms the candidate: it must neither send nor trigger a shortcut.
  if (isImeComposing(event)) {
    return;
  }

  if (event.key === 'Backspace' && ctx.inputMessage === '') {
    const lastRemovableChip = [...ctx.chips].reverse().find((chip) => chip.isRemovable && chip.onRemove);
    if (lastRemovableChip) {
      event.preventDefault();
      lastRemovableChip.onRemove?.();
      return;
    }
  }

  if (ctx.editorExpanded && event.key === 'Escape') {
    event.preventDefault();
    ctx.setEditorExpanded(false);
    return;
  }

  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && event.shiftKey) {
    event.preventDefault();
    ctx.setEditorExpanded((expanded) => !expanded);
    return;
  }

  if (ctx.showCommandPalette) {
    ctx.onCommandKeyDown(event);
    return;
  }
  if (ctx.showReferenceMention && ctx.onReferenceMentionKeyDown(event)) {
    return;
  }

  if (ctx.inputHistory.handleKeyDown(event)) {
    if (ctx.inputHistory.popup.open && (event.key === 'Tab' || event.key === 'Enter')) {
      const text = ctx.inputHistory.confirm();
      if (text) {
        ctx.setInputMessage(text);
      }
    }
    return;
  }

  const dualAction = resolveDualChannelAction(event, { loading: ctx.loading, expanded: ctx.editorExpanded });
  if (dualAction === 'queue') {
    void ctx.queue();
  } else if (dualAction === 'submit') {
    void ctx.submit();
  }
}
