import { blockedReasonText } from '@/lib/kanban/kanbanBlockedReason';
import type { toast } from '@/lib/utils/toast';

export type KanbanTaskToastTranslator = (key: string) => string;

export interface KanbanTaskToastDeps {
  /** Translator of the `notifications` namespace (status labels). */
  t: KanbanTaskToastTranslator;
  /** Translator of the `kanban` namespace (blocked reasons). */
  tKanban: KanbanTaskToastTranslator;
  pushToast: { [K in 'success' | 'warning']: (...args: Parameters<(typeof toast)[K]>) => void };
  notifyIfLeader: (title: string, body?: string) => void;
}

const TERMINAL_STATUSES = ['completed', 'blocked', 'failed'];
const MAX_DESCRIPTION_LENGTH = 200;

function statusLabelKey(status: string): string {
  if (status === 'completed') {
    return 'kanbanTaskCompleted';
  }
  return status === 'blocked' ? 'kanbanTaskBlocked' : 'kanbanTaskFailed';
}

function clipDescription(text: string): string {
  return text.length > MAX_DESCRIPTION_LENGTH ? `${text.slice(0, MAX_DESCRIPTION_LENGTH - 1)}…` : text;
}

/**
 * Toast and system notification for a kanban task that completed, blocked or failed.
 * The server sends the reason as written (`detail`); a blocked reason it knows is shown in the interface language.
 * A scheduled block is silent: the task resumes by itself and its card shows when.
 */
export function showKanbanTaskToast(data: Record<string, unknown>, deps: KanbanTaskToastDeps): void {
  const action = String(data.action ?? '');
  const title = String(data.title ?? data.task_id ?? '');
  const isTerminal =
    action === 'task_completed' ||
    action === 'task_blocked' ||
    action === 'task_failed' ||
    (action === 'moved' && TERMINAL_STATUSES.includes(String(data.status ?? '')));
  if (!isTerminal || !title) {
    return;
  }

  const { t, tKanban, pushToast, notifyIfLeader } = deps;
  const status = String(data.status ?? '') || action.replace('task_', '');
  if (status === 'blocked' && data.block_kind === 'scheduled') {
    return;
  }
  const label = `${t(statusLabelKey(status))}: ${title}`;
  const detail = String(data.detail ?? '');
  const description = detail ? clipDescription(blockedReasonText(detail, tKanban)) : undefined;

  if (status === 'completed') {
    pushToast.success(label, { description, duration: 8_000, dismissible: true });
  } else {
    pushToast.warning(label, { description, duration: 10_000, dismissible: true });
  }
  notifyIfLeader(label, description);
}
