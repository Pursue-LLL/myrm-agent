/**
 * [INPUT]
 * - @/services/contextCompaction::compactChat (POS: 上下文压缩请求)
 * - @/services/chat::focusFlushChat (POS: 清空聊天记录请求)
 * - @/store/useChatStore (POS: 活跃聊天、消息重载与会话状态重置)
 * - @/services/i18nToastService::showI18nToast (POS: i18n toast 封装)
 *
 * [OUTPUT]
 * - executeCompactSlashCommand: 执行 /compact 命令（压缩当前会话上下文，可带聚焦主题）
 * - executeFocusSlashCommand: 执行 /focus 命令（清空聊天记录并保留沙箱环境）
 *
 * [POS]
 * 管理会话上下文体量的原生 Slash 命令执行服务。供 builtinActions 调用。
 */

import { toast } from 'sonner';
import { focusFlushChat } from '@/services/chat';
import { compactChat } from '@/services/contextCompaction';
import { showI18nToast } from '@/services/i18nToastService';
import type { ActionResult } from '@/types/command';

export async function executeCompactSlashCommand(inputValue: string): Promise<ActionResult> {
  const { default: useChatStore } = await import('@/store/useChatStore');
  const { chatId, loadMessages } = useChatStore.getState();

  if (!chatId) {
    return { success: false, error: 'No active chat' };
  }

  const focusTopic = inputValue.replace(/^\/compact\s*/i, '').trim() || undefined;

  const skipWarning = localStorage.getItem('dontRemindCompact') === 'true';
  if (!skipWarning) {
    showI18nToast('commands.builtin.compactToast', undefined, {
      type: 'info',
      duration: 5000,
    });
  }

  const toastId = toast.loading('…');
  try {
    const result = await compactChat(chatId, focusTopic);
    if (result.compacted) {
      showI18nToast(
        'commands.builtin.compacted',
        {
          messageCount: result.message_count,
          tokensSaved: result.tokens_saved,
        },
        { type: 'success' },
      );
      toast.dismiss(toastId);
      await loadMessages(chatId);
    } else {
      showI18nToast('commands.builtin.nothingToCompact', undefined, {
        description: result.reason ?? undefined,
        type: 'info',
      });
      toast.dismiss(toastId);
    }
    return { success: true, newInputValue: '' };
  } catch {
    showI18nToast('commands.builtin.compactionFailed', undefined, { type: 'error' });
    toast.dismiss(toastId);
    return { success: false, error: 'Compaction failed' };
  }
}

export async function executeFocusSlashCommand(): Promise<ActionResult> {
  const { default: useChatStore } = await import('@/store/useChatStore');
  const { chatId, resetSessionState, loadMessages, stopMessage } = useChatStore.getState();

  if (!chatId) {
    return { success: false, error: 'No active chat' };
  }

  const toastId = toast.loading('…');
  try {
    stopMessage();

    const result = await focusFlushChat(chatId);
    if (result.cleared) {
      showI18nToast('commands.builtin.focusSuccess', undefined, { type: 'success' });
      toast.dismiss(toastId);
      resetSessionState();
      await loadMessages(chatId);
    }
    return { success: true, newInputValue: '' };
  } catch {
    showI18nToast('commands.builtin.focusFailed', undefined, { type: 'error' });
    toast.dismiss(toastId);
    return { success: false, error: 'Focus flush failed' };
  }
}
