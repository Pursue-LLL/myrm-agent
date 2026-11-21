/**
 * [INPUT]
 * - @/store/useChatStore (POS: 活跃聊天、流式状态与目标模式开关)
 * - @/lib/api::fetchWithTimeout (POS: 目标状态查询)
 * - @/store/chat/goals/goalActionClient::postGoalAction (POS: 目标暂停 / 恢复 / 取消请求)
 * - @/services/i18nToastService::showI18nToast (POS: i18n toast 封装)
 *
 * [OUTPUT]
 * - executeGoalSlashCommand: 执行 /goal 命令（设置目标，或 status / pause / resume / clear 子命令）
 *
 * [POS]
 * 原生 /goal Slash 命令执行服务。供 builtinActions 调用。
 */

import { showI18nToast } from '@/services/i18nToastService';
import type { ActionResult } from '@/types/command';

export async function executeGoalSlashCommand(inputValue: string): Promise<ActionResult> {
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

  /** Sends a goal control; a goal still finishing its last step gets its own notice, not "command failed". */
  const controlGoal = async (action: 'pause' | 'resume' | 'cancel', doneKey: string): Promise<ActionResult> => {
    const { postGoalAction } = await import('@/store/chat/goals/goalActionClient');
    const outcome = await postGoalAction(chatId, action);
    if (outcome === 'done') {
      showI18nToast(doneKey, undefined, { type: 'success' });
      return { success: true, newInputValue: '' };
    }
    if (outcome !== 'held') {
      showI18nToast(
        outcome === 'busy' ? 'commands.builtin.goalActionBusy' : 'commands.builtin.goalActionFailed',
        undefined,
        {
          type: 'error',
        },
      );
    }
    return { success: false, error: 'Goal command failed' };
  };

  try {
    if (goalSubcommands.has(firstToken)) {
      if (firstToken === 'status') {
        const res = await fetchWithTimeout(`/goals/${chatId}/status`);
        if (!res.ok) {
          throw new Error(`Goal status failed with HTTP ${res.status}`);
        }
        const data = (await res.json()) as { goal?: { status?: string } | null };
        if (!data.goal?.status) {
          showI18nToast('commands.builtin.goalNoActive', undefined, { type: 'info' });
        } else {
          showI18nToast('commands.builtin.goalStatus', { status: data.goal.status }, { type: 'info' });
        }
        return { success: true, newInputValue: '' };
      }
      if (firstToken === 'pause') {
        return await controlGoal('pause', 'commands.builtin.goalPaused');
      }
      if (firstToken === 'resume') {
        return await controlGoal('resume', 'commands.builtin.goalResumed');
      }
      if (firstToken === 'clear' || firstToken === 'cancel') {
        return await controlGoal('cancel', 'commands.builtin.goalCleared');
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
}
