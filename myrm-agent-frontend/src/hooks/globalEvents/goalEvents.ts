/**
 * [INPUT]
 * - @/store/chat/goals/useGoalStore::fetchQueue (POS: 目标队列)
 *
 * [OUTPUT]
 * - goalEventHandlers: 目标结束 / 出队事件的处理器表
 *
 * [POS]
 * 全局事件中目标（goal）的生命周期提示：结果或下一目标开始时提示用户，点击直达对应会话。
 */
import type { GlobalEventDeps, GlobalEventHandler } from './eventTypes';

const GOAL_OBJECTIVE_MAX_LENGTH = 100;

const GOAL_TERMINAL_LABEL_KEYS: Readonly<Record<string, string>> = {
  complete: 'goalCompleted',
  cancelled: 'goalCancelled',
  budget_limited: 'goalBudgetLimited',
  needs_human_review: 'goalNeedsReview',
};

/** Opens the goal's chat, or nothing when the event names no session. */
function chatOpener({ router }: GlobalEventDeps, sessionId: string): (() => void) | undefined {
  return sessionId ? () => router.push(`/chat/${sessionId}`) : undefined;
}

const handleGoalTerminal: GlobalEventHandler = (payload, deps) => {
  const { t, pushToast, notifyIfLeader } = deps;
  const status = String(payload.data.status ?? '');
  const objective = String(payload.data.objective ?? '').slice(0, GOAL_OBJECTIVE_MAX_LENGTH);
  const sessionId = String(payload.data.session_id ?? '');
  const statusLabel = t(GOAL_TERMINAL_LABEL_KEYS[status] ?? 'goalTerminal');
  if (status === 'complete') {
    pushToast.success(statusLabel, { description: objective, duration: 8_000, dismissible: true });
  } else {
    pushToast.warning(statusLabel, { description: objective, duration: 10_000, dismissible: true });
  }
  notifyIfLeader(statusLabel, objective, chatOpener(deps, sessionId));
  window.dispatchEvent(new CustomEvent('goal_terminal', { detail: payload.data }));
};

const handleGoalDequeued: GlobalEventHandler = (payload, deps) => {
  const { t, pushToast, notifyIfLeader } = deps;
  const objective = String(payload.data.objective ?? '').slice(0, GOAL_OBJECTIVE_MAX_LENGTH);
  const sessionId = String(payload.data.session_id ?? '');
  const label = t('goalDequeued');
  pushToast.info(label, { description: objective, duration: 6_000, dismissible: true });
  notifyIfLeader(label, objective, chatOpener(deps, sessionId));
  if (sessionId) {
    import('@/store/chat/goals/useGoalStore').then(({ useGoalStore }) => {
      useGoalStore.getState().fetchQueue(sessionId);
    });
  }
  window.dispatchEvent(new CustomEvent('goal_dequeued', { detail: payload.data }));
};

export const goalEventHandlers: Record<string, GlobalEventHandler> = {
  goal_terminal: handleGoalTerminal,
  goal_dequeued: handleGoalDequeued,
};
