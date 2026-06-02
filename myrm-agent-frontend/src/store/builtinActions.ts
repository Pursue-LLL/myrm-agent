import type { SlashAction } from '@/types/command';
import { compactChat, focusFlushChat } from '@/services/chat';
import { showI18nToast } from '@/services/i18nToastService';
import { toast } from 'sonner';

export function buildBuiltinActions(): SlashAction[] {
  return [
    {
      id: 'builtin:compact',
      name: 'compact',
      description: 'commands.builtin.compact',
      type: 'action',
      execute: async (inputValue: string) => {
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
              description: result.reason,
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
      },
    },
    {
      id: 'builtin:focus',
      name: 'focus',
      description: 'commands.builtin.focus',
      type: 'action',
      execute: async () => {
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
      },
    },
  ];
}
