import type { SlashAction } from '@/types/command';
import { compactChat, focusFlushChat } from '@/services/chat';
import { showI18nToast } from '@/services/i18nToastService';
import { toast } from 'sonner';

function parseYoloArgs(inputValue: string): { action: 'toggle' | 'on' | 'off'; timeout?: number } {
  const args = inputValue.replace(/^\/yolo\s*/i, '').trim().toLowerCase();
  if (!args) {return { action: 'toggle' };}
  if (args === 'on') {return { action: 'on' };}
  if (args === 'off') {return { action: 'off' };}

  const timeoutMatch = args.match(/^(?:on\s+)?(\d+)\s*([smh]?)$/);
  if (timeoutMatch) {
    let seconds = parseInt(timeoutMatch[1], 10);
    const unit = timeoutMatch[2] || 's';
    if (unit === 'm') {seconds *= 60;}
    else if (unit === 'h') {seconds *= 3600;}
    return { action: 'on', timeout: seconds };
  }
  return { action: 'toggle' };
}

export function buildBuiltinActions(): SlashAction[] {
  return [
    {
      id: 'builtin:compact',
      name: 'compact',
      description: 'commands.builtin.compact',
      argsHint: '[topic]',
      aliases: ['compress'],
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
    {
      id: 'builtin:yolo',
      name: 'yolo',
      description: 'commands.builtin.yolo',
      argsHint: '[on|off|<seconds>]',
      type: 'action',
      execute: async (inputValue: string) => {
        const { getConfigSyncManager } = await import('@/services/config');
        const syncManager = getConfigSyncManager();
        const config = syncManager.get('securityConfig');
        if (!config) {
          return { success: false, error: 'Security config not loaded yet' };
        }
        const { action, timeout } = parseYoloArgs(inputValue);

        const currentlyEnabled = config.yoloModeEnabled ?? false;

        let newEnabled: boolean;
        if (action === 'toggle') {newEnabled = !currentlyEnabled;}
        else if (action === 'on') {newEnabled = true;}
        else {newEnabled = false;}

        syncManager.set('securityConfig', {
          ...config,
          yoloModeEnabled: newEnabled,
          ...(newEnabled && timeout ? { yoloModeTimeout: timeout } : { yoloModeTimeout: undefined }),
          ...(newEnabled ? { yoloModeEnabledAt: Math.floor(Date.now() / 1000) } : { yoloModeEnabledAt: undefined }),
        });

        if (newEnabled) {
          const suffix = timeout ? ` (${timeout}s)` : '';
          showI18nToast('commands.builtin.yoloEnabled', { timeout: suffix }, { type: 'warning' });
        } else {
          showI18nToast('commands.builtin.yoloDisabled', undefined, { type: 'success' });
        }

        return { success: true, newInputValue: '' };
      },
    },
    {
      id: 'builtin:freeze',
      name: 'freeze',
      description: 'commands.builtin.freeze',
      argsHint: '[off|resume]',
      aliases: ['estop'],
      type: 'action',
      execute: async (inputValue: string) => {
        const { apiRequest } = await import('@/lib/api');
        const args = inputValue.replace(/^\/freeze\s*/i, '').trim().toLowerCase();
        const shouldResume = args === 'off' || args === 'resume';

        const toastId = toast.loading('…');
        try {
          await apiRequest<{ level: string; reason: string }>('/security/estop', {
            method: 'POST',
            body: JSON.stringify(
              shouldResume
                ? { action: 'resume' }
                : { action: 'activate', reason: 'User triggered /freeze' },
            ),
          });

          toast.dismiss(toastId);
          if (shouldResume) {
            showI18nToast('commands.builtin.freezeResumed', undefined, { type: 'success' });
          } else {
            showI18nToast('commands.builtin.freezeActivated', undefined, { type: 'warning' });
          }
          window.dispatchEvent(new Event('estop-changed'));
          return { success: true, newInputValue: '' };
        } catch (e) {
          toast.dismiss(toastId);
          const msg = e instanceof Error ? e.message : 'Unknown error';
          showI18nToast('commands.builtin.freezeFailed', undefined, { type: 'error' });
          return { success: false, error: msg };
        }
      },
    },
    {
      id: 'builtin:new',
      name: 'new',
      description: 'commands.builtin.new',
      aliases: ['reset'],
      type: 'action',
      execute: async () => {
        const { default: useWorkspaceStore } = await import('@/store/useWorkspaceStore');
        useWorkspaceStore.getState().addPane();
        return { success: true, newInputValue: '' };
      },
    },
    {
      id: 'builtin:stop',
      name: 'stop',
      description: 'commands.builtin.stop',
      aliases: ['cancel', 'abort'],
      type: 'action',
      execute: async () => {
        const { default: useChatStore } = await import('@/store/useChatStore');
        const { chatId } = useChatStore.getState();
        if (!chatId) {
          return { success: false, error: 'No active chat' };
        }
        useChatStore.getState().stopMessage();
        showI18nToast('commands.builtin.stopped', undefined, { type: 'info' });
        return { success: true, newInputValue: '' };
      },
    },
    {
      id: 'builtin:model',
      name: 'model',
      description: 'commands.builtin.model',
      aliases: ['switch-model'],
      type: 'action',
      execute: async () => {
        showI18nToast('commands.builtin.modelHint', undefined, { type: 'info', duration: 4000 });
        return { success: true, newInputValue: '' };
      },
    },
    {
      id: 'builtin:learn',
      name: 'learn',
      description: 'commands.builtin.learn',
      argsHint: '<URL|path|description>',
      type: 'action',
      execute: async (inputValue: string) => {
        const { submitLearnMessage } = await import('@/lib/skills/submitLearnMessage');
        const result = await submitLearnMessage({ input: inputValue });
        if (!result.ok) {
          if (result.reason === 'no_chat') {
            showI18nToast('chat.sendBlocked.title', undefined, {
              descriptionKey: 'chat.sendBlocked.noChatDescription',
              type: 'warning',
            });
            return { success: false, error: 'No active chat' };
          }
          if (result.reason === 'busy') {
            showI18nToast('chat.extractToSkill.busy', undefined, { type: 'warning' });
            return { success: false, error: 'Chat is busy' };
          }
          if (result.reason === 'empty') {
            return { success: true, newInputValue: '/learn' };
          }
          showI18nToast('chat.extractToSkill.error', undefined, { type: 'error' });
          return { success: false, error: 'Learn failed' };
        }
        showI18nToast('chat.extractToSkill.started', undefined, { type: 'info' });
        return { success: true, newInputValue: '' };
      },
    },
    {
      id: 'builtin:fork',
      name: 'fork',
      description: 'commands.builtin.fork',
      argsHint: '[title]',
      aliases: ['branch'],
      type: 'action',
      execute: async (inputValue: string) => {
        const { default: useChatStore } = await import('@/store/useChatStore');
        const { chatId, messages, loading } = useChatStore.getState();

        if (!chatId) {
          return { success: false, error: 'No active chat' };
        }

        if (loading) {
          showI18nToast('commands.builtin.forkStreamingBlocked', undefined, { type: 'warning' });
          return { success: false, error: 'Cannot fork while streaming' };
        }

        if (messages.length === 0) {
          showI18nToast('commands.builtin.forkEmpty', undefined, { type: 'info' });
          return { success: false, error: 'No messages to fork from' };
        }

        const title = inputValue.replace(/^\/fork\s*/i, '').trim() || undefined;
        const lastIndex = messages.length - 1;

        const toastId = toast.loading('…');
        try {
          const { forkConversation } = await import('@/services/fork-api');
          const response = await forkConversation(chatId, lastIndex, title);

          if (response.success && response.data.new_chat_id) {
            toast.dismiss(toastId);
            showI18nToast('commands.builtin.forkSuccess', undefined, { type: 'success' });

            const { default: useWorkspaceStore } = await import('@/store/useWorkspaceStore');
            useWorkspaceStore.getState().addPane(response.data.new_chat_id);
          } else {
            throw new Error('Fork failed');
          }
          return { success: true, newInputValue: '' };
        } catch {
          toast.dismiss(toastId);
          showI18nToast('commands.builtin.forkFailed', undefined, { type: 'error' });
          return { success: false, error: 'Fork failed' };
        }
      },
    },
    {
      id: 'builtin:goal',
      name: 'goal',
      description: 'commands.builtin.goal',
      argsHint: '<objective> | status | pause | resume | clear',
      type: 'action',
      execute: async (inputValue: string) => {
        const { default: useChatStore } = await import('@/store/useChatStore');
        const { fetchWithTimeout } = await import('@/lib/api');
        const { chatId, loading, setIsGoalMode, setInputMessage } = useChatStore.getState();

        if (!chatId) {
          showI18nToast('commands.builtin.noActiveChat', undefined, { type: 'info' });
          return { success: false, error: 'No active chat' };
        }

        const args = inputValue.replace(/^\/goal\s*/i, '').trim();
        if (!args) {
          showI18nToast('commands.builtin.goalUsage', undefined, { type: 'info' });
          return { success: false, error: 'Missing goal arguments' };
        }

        const firstToken = args.split(/\s+/)[0]?.toLowerCase() ?? '';
        const goalSubcommands = new Set(['status', 'pause', 'resume', 'clear', 'cancel']);

        const postGoalAction = async (action: string) => {
          await fetchWithTimeout(`/goals/${chatId}/status`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action }),
          });
        };

        try {
          if (goalSubcommands.has(firstToken)) {
            if (firstToken === 'status') {
              const res = await fetchWithTimeout(`/goals/${chatId}/status`);
              const data = (await res.json()) as { goal?: { status?: string } | null };
              if (!data.goal?.status) {
                showI18nToast('commands.builtin.goalNoActive', undefined, { type: 'info' });
              } else {
                showI18nToast('commands.builtin.goalStatus', { status: data.goal.status }, { type: 'info' });
              }
              return { success: true, newInputValue: '' };
            }
            if (firstToken === 'pause') {
              await postGoalAction('pause');
              showI18nToast('commands.builtin.goalPaused', undefined, { type: 'success' });
              return { success: true, newInputValue: '' };
            }
            if (firstToken === 'resume') {
              await postGoalAction('resume');
              showI18nToast('commands.builtin.goalResumed', undefined, { type: 'success' });
              return { success: true, newInputValue: '' };
            }
            if (firstToken === 'clear' || firstToken === 'cancel') {
              await postGoalAction('cancel');
              showI18nToast('commands.builtin.goalCleared', undefined, { type: 'success' });
              return { success: true, newInputValue: '' };
            }
          }

          if (loading) {
            showI18nToast('chat.fork.streamingBlocked', undefined, { type: 'warning' });
            return { success: false, error: 'Cannot set goal while streaming' };
          }

          setIsGoalMode(true);
          setInputMessage(args);
          showI18nToast('commands.builtin.goalSet', undefined, { type: 'info' });
          return { success: true, newInputValue: '' };
        } catch {
          showI18nToast('commands.builtin.goalActionFailed', undefined, { type: 'error' });
          return { success: false, error: 'Goal command failed' };
        }
      },
    },
    {
      id: 'builtin:ask',
      name: 'ask',
      description: 'commands.builtin.ask',
      argsHint: '[question]',
      aliases: ['side'],
      type: 'action',
      execute: async (inputValue: string) => {
        const args = inputValue.replace(/^\/(?:ask|side)\s*/i, '').trim();
        window.dispatchEvent(
          new CustomEvent('copilot-open-advisor', {
            detail: { question: args },
          }),
        );
        return { success: true, newInputValue: '' };
      },
    },
    {
      id: 'builtin:pet',
      name: 'pet',
      description: 'commands.builtin.pet',
      argsHint: '[toggle | list | <slug>]',
      aliases: ['pets'],
      type: 'action',
      execute: async (inputValue: string) => {
        const { executePetSlashCommand } = await import('@/services/companion/petSlashCommand');
        return executePetSlashCommand(inputValue);
      },
    },
  ];
}
