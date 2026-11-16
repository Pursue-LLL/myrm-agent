/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: Active chat state manager.)
 * - @/store/chat/types::GoalStatusPayload (POS: @/store/chat/types 稳定入口；实现位于 types/。)
 * - @/store/chat/goals/useGoalStore::useGoalStore
 * - @/services/backgroundTasksRefresh::notifyBackgroundTasksChangedForShellJobFinish
 * - @/lib/api::fetchWithTimeout (POS: 前端 API 接入层。)
 * - @/store/chat/useRewindStore::useRewindStore (POS: UI state manager for rewind dialog target.)
 * - @/components/dev/e2eBridge/members/types::E2eBridgeMembers (POS: 桥成员分组的类型)
 *
 * [OUTPUT]
 * - createGoalMembers(): goal mode and draft, rewind dialog, system notifications and background-job finish dispatch
 *
 * [POS]
 * 桥成员（目标与回退）：Goal 模式与草稿、回退对话框、系统通知与后台任务结束分发。
 */
import { flushSync } from 'react-dom';
import useChatStore from '@/store/useChatStore';
import type { GoalStatusPayload } from '@/store/chat/types';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import { notifyBackgroundTasksChangedForShellJobFinish } from '@/services/backgroundTasksRefresh';
import { fetchWithTimeout } from '@/lib/api';
import { useRewindStore } from '@/store/chat/useRewindStore';
import type { E2eBridgeMembers } from '@/components/dev/e2eBridge/members/types';

export function createGoalMembers(): E2eBridgeMembers {
  return {
    setGoalMode: (enabled: boolean) => {
      flushSync(() => {
        useChatStore.getState().setIsGoalMode(enabled);
      });
    },
    setGoalBudgetTokens: (tokens: number | null) => {
      flushSync(() => {
        useChatStore.getState().setGoalBudgetTokens(tokens);
      });
    },
    setGoalConvergenceWindow: (window: number | null) => {
      flushSync(() => {
        useChatStore.getState().setGoalConvergenceWindow(window);
      });
    },
    getGoalMode: () => useChatStore.getState().isGoalMode,
    openRewindDialog: (userIndex = 1) => {
      const state = useChatStore.getState();
      const userEntries: Array<{ messageId: string; index: number }> = [];
      state.messages.forEach((m, idx) => {
        if (m.role === 'user') {
          userEntries.push({ messageId: m.messageId, index: idx });
        }
      });
      const targetEntry = userEntries[userIndex] || userEntries[0] || null;
      if (targetEntry && state.chatId) {
        useRewindStore.getState().openRewind({
          chatId: state.chatId,
          messageId: targetEntry.messageId,
          messageIndex: targetEntry.index,
        });
        return true;
      }
      return false;
    },
    closeRewindDialog: () => {
      useRewindStore.getState().closeRewind();
    },
    getRewindTarget: () => useRewindStore.getState().target,
    getActiveGoalSnapshot: () => {
      const goal = useGoalStore.getState().activeGoal;
      if (!goal) {
        return null;
      }
      return {
        status: goal.status,
        reason: goal.reason ?? null,
        objective: goal.objective,
      };
    },
    loadActiveGoalFromApi: async () => {
      const chatId = useChatStore.getState().chatId?.trim();
      if (!chatId) {
        return { ok: false, err: 'no-chat-id' };
      }
      const res = await fetchWithTimeout(`/goals/${chatId}/status`);
      if (!res.ok) {
        return { ok: false, err: `fetch-${res.status}` };
      }
      const data = (await res.json()) as { goal?: Record<string, unknown> };
      if (!data.goal) {
        return { ok: false, err: 'no-goal' };
      }
      const { normalizeGoalState } = await import('@/store/chat/messageStream/streamHelpers');
      const goalState = normalizeGoalState(data.goal as unknown as GoalStatusPayload);
      useGoalStore.getState().setActiveGoal(chatId, goalState);
      // The store takes only the goal of the chat it is bound to; report a write it dropped instead of success.
      if (useGoalStore.getState().activeGoal?.goalId !== goalState.goalId) {
        return { ok: false, err: 'goal-store-not-bound-to-chat' };
      }
      return {
        ok: true,
        status: String(data.goal.status ?? ''),
        reason: typeof data.goal.reason === 'string' ? data.goal.reason : null,
      };
    },
    getGoalDraftState: () => {
      const state = useChatStore.getState();
      return {
        composerObjective: state.inputMessage.trim(),
        acceptanceCount: state.goalAcceptanceCriteria?.length ?? 0,
        constraintsCount: state.goalConstraints?.length ?? 0,
        draftButtonDisabled: !state.inputMessage.trim(),
      };
    },
    ephSubagentsStatus: () => {
      const ac = useChatStore.getState().agentConfig;
      return {
        hasConfig: Boolean(ac),
        ephKeys: ac?.ephemeralSubagents ? Object.keys(ac.ephemeralSubagents) : [],
        applied: window.__MYRM_E2E_EPH_APPLIED__ ?? null,
        sendOpts: window.__MYRM_E2E_EPH_OPTS__ ?? null,
      };
    },
    runGoalDraftFromComposer: async () => {
      const objective = useChatStore.getState().inputMessage.trim();
      if (!objective) {
        return { ok: false, err: 'empty-composer' };
      }
      const locale =
        typeof document.documentElement.lang === 'string' && document.documentElement.lang
          ? document.documentElement.lang
          : 'en';
      const res = await fetchWithTimeout(
        '/goals/draft',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ objective, locale }),
        },
        120_000,
      );
      if (!res.ok) {
        return { ok: false, err: `draft-${res.status}` };
      }
      const data = (await res.json()) as {
        constraints?: string[];
        acceptance_criteria?: Array<Record<string, unknown>>;
      };
      if (data.acceptance_criteria?.length) {
        useChatStore.getState().setGoalAcceptanceCriteria(data.acceptance_criteria);
      }
      if (data.constraints?.length) {
        useChatStore.getState().setGoalConstraints(data.constraints);
      }
      return {
        ok: true,
        acceptanceCount: data.acceptance_criteria?.length ?? 0,
        constraintsCount: data.constraints?.length ?? 0,
      };
    },
    dispatchSystemNotification: (detail: Record<string, unknown>) => {
      window.dispatchEvent(new CustomEvent('system-notification', { detail }));
      const data = detail.data;
      const meta =
        typeof data === 'object' && data !== null && !Array.isArray(data)
          ? (data as Record<string, unknown>).meta_data
          : undefined;
      const kind =
        typeof meta === 'object' && meta !== null && !Array.isArray(meta)
          ? (meta as Record<string, unknown>).kind
          : undefined;
      const chatId =
        typeof meta === 'object' && meta !== null && !Array.isArray(meta)
          ? (meta as Record<string, unknown>).chat_id
          : undefined;
      if (kind === 'background_job_finish' && typeof chatId === 'string' && chatId.trim()) {
        void useGoalStore.getState().refreshActiveGoal(chatId.trim());
        notifyBackgroundTasksChangedForShellJobFinish(meta as Record<string, unknown>);
      }
    },
    dispatchBackgroundJobFinishAndRefresh: async (chatId: string) => {
      const trimmed = chatId.trim();
      if (!trimmed) {
        return { ok: false, err: 'empty-chat-id' };
      }
      const detail = {
        data: {
          meta_data: { kind: 'background_job_finish', chat_id: trimmed },
        },
      };
      window.dispatchEvent(new CustomEvent('system-notification', { detail }));
      await useGoalStore.getState().refreshActiveGoal(trimmed);
      notifyBackgroundTasksChangedForShellJobFinish(detail.data.meta_data as Record<string, unknown>);
      const snap = useGoalStore.getState().activeGoal;
      return {
        ok: true,
        status: snap?.status ?? null,
        reason: snap?.reason ?? null,
      };
    },
  } as E2eBridgeMembers;
}
