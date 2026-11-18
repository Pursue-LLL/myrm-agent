/**
 * [INPUT]
 * - @/services/commands/* (POS: /compact、/focus、/goal、/yolo、/freeze、/loop 的执行服务，按需加载)
 *
 * [OUTPUT]
 * - buildBuiltinActions: 内置 Slash 命令注册表
 *
 * [POS]
 * 内置 Slash 命令定义。体量较大的命令把执行体交给 services/commands，注册表只保留元数据与委托。
 */

import type { SlashAction } from '@/types/command';
import { showI18nToast } from '@/services/i18nToastService';
import { toast } from 'sonner';

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
        const { executeCompactSlashCommand } = await import('@/services/commands/contextSlashCommands');
        return executeCompactSlashCommand(inputValue);
      },
    },
    {
      id: 'builtin:focus',
      name: 'focus',
      description: 'commands.builtin.focus',
      type: 'action',
      execute: async () => {
        const { executeFocusSlashCommand } = await import('@/services/commands/contextSlashCommands');
        return executeFocusSlashCommand();
      },
    },
    {
      id: 'builtin:yolo',
      name: 'yolo',
      description: 'commands.builtin.yolo',
      argsHint: '[on|off|<seconds>]',
      type: 'action',
      execute: async (inputValue: string) => {
        const { executeYoloSlashCommand } = await import('@/services/commands/securitySlashCommands');
        return executeYoloSlashCommand(inputValue);
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
        const { executeFreezeSlashCommand } = await import('@/services/commands/securitySlashCommands');
        return executeFreezeSlashCommand(inputValue);
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
          if (result.reason === 'refused') {
            // The send already told the user why; leaving newInputValue unset keeps the typed command for a retry.
            return { success: false, error: 'Learn refused' };
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
        const { executeGoalSlashCommand } = await import('@/services/commands/goalSlashCommand');
        return executeGoalSlashCommand(inputValue);
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
        if (typeof window !== 'undefined') {
          window.dispatchEvent(
            new CustomEvent('copilot-open-advisor', {
              detail: { question: args },
            }),
          );
        }
        return { success: true, newInputValue: '' };
      },
    },
    {
      id: 'builtin:loop',
      name: 'loop',
      description: 'commands.builtin.loop',
      argsHint: '[--interval <time>] [--times <N>] [--until <cond>] <prompt> | status | stop',
      aliases: ['repeat'],
      type: 'action',
      execute: async (inputValue: string) => {
        const { executeLoopSlashCommand } = await import('@/services/commands/loopSlashCommand');
        return executeLoopSlashCommand(inputValue);
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
    {
      id: 'builtin:memo',
      name: 'memo',
      description: 'commands.builtin.memo',
      argsHint: '[transcript | topic]',
      aliases: ['meeting', 'minutes'],
      type: 'action',
      execute: async (inputValue: string) => {
        const { default: useChatStore } = await import('@/store/useChatStore');
        const { setInputMessage } = useChatStore.getState();
        const rawArgs = inputValue.replace(/^\/(?:memo|meeting|minutes)\s*/i, '').trim();
        const directive = rawArgs
          ? `/memo ${rawArgs}`
          : '/memo 请根据本次语音/会议录音，整理结构化会议纪要工件、派发看板待办并沉淀核心决策至记忆。';
        setInputMessage(directive);
        return { success: true, newInputValue: directive };
      },
    },
    {
      id: 'builtin:review-week',
      name: 'review-week',
      description: 'commands.builtin.review_week',
      argsHint: '[timeframe | focus-area]',
      aliases: ['week-review', 'weekly-digest', 'extract-blockers'],
      type: 'action',
      execute: async (inputValue: string) => {
        const { default: useChatStore } = await import('@/store/useChatStore');
        const { setInputMessage } = useChatStore.getState();
        const rawArgs = inputValue
          .replace(/^\/(?:review-week|week-review|weekly-digest|extract-blockers)\s*/i, '')
          .trim();
        const directive = rawArgs
          ? `/review-week ${rawArgs}`
          : '/review-week 请检索本周的会议录音、听记素材与看板状态，提炼全局工作结论与关键阻碍并生成周度复盘工件。';
        setInputMessage(directive);
        return { success: true, newInputValue: directive };
      },
    },
    {
      id: 'builtin:design-image',
      name: 'design-image',
      description: 'commands.builtin.design_image',
      argsHint: '<prompt | visual brief>',
      aliases: ['image-design', 'prompt-image', 'style-image'],
      type: 'action',
      execute: async (inputValue: string) => {
        const { default: useChatStore } = await import('@/store/useChatStore');
        const { setInputMessage } = useChatStore.getState();
        const rawArgs = inputValue.replace(/^\/(?:design-image|image-design|prompt-image|style-image)\s*/i, '').trim();
        const directive = rawArgs
          ? `/design-image ${rawArgs}`
          : '/design-image 请基于结构化 Prompt-as-Code 原子视觉规范，为我设计一张商业级视觉配图（包含主体、风格、光影、材质与构图）。';
        setInputMessage(directive);
        return { success: true, newInputValue: directive };
      },
    },
    {
      id: 'builtin:export',
      name: 'export',
      description: 'commands.builtin.export',
      argsHint: '[html|md|json|zip|copy]',
      aliases: ['save', 'share'],
      type: 'action',
      execute: async (inputValue: string) => {
        const { default: useChatStore } = await import('@/store/useChatStore');
        const { chatId } = useChatStore.getState();
        if (!chatId) {
          return { success: false, error: 'No active chat' };
        }
        const rawArgs = inputValue
          .replace(/^\/(?:export|save|share)\s*/i, '')
          .trim()
          .toLowerCase();

        if (rawArgs === 'copy') {
          const { exportChat } = await import('@/services/chat');
          const { copyAsMarkdown } = await import('@/lib/utils/chat-export');
          try {
            const data = await exportChat(chatId, { redactSecrets: true });
            await copyAsMarkdown(data);
            showI18nToast('chat.exportChat.copySuccessRedacted', undefined, { type: 'success' });
            return { success: true, newInputValue: '' };
          } catch {
            return { success: false, error: 'Copy failed' };
          }
        }

        if (typeof window !== 'undefined') {
          window.dispatchEvent(
            new CustomEvent('myrm:open-session-export', {
              detail: { chatId, format: rawArgs || undefined },
            }),
          );
        }
        return { success: true, newInputValue: '' };
      },
    },
    {
      id: 'builtin:context',
      name: 'context',
      description: 'commands.builtin.context',
      aliases: ['footprint', 'ctx'],
      type: 'action',
      execute: async () => {
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('myrm:open-context-inspector'));
        }
        return { success: true, newInputValue: '' };
      },
    },
  ];
}
