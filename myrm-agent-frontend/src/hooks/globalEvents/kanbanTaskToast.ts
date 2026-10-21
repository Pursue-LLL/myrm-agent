/**
 * [INPUT]
 * @/lib/kanban/kanbanBlockedReason::blockedReasonText (POS: 服务端阻塞原因的界面语言文案)
 * @/lib/kanban/kanbanChatBoard::buildKanbanBoardDeepLink (POS: 看板深链 SSOT)
 *
 * [OUTPUT]
 * showKanbanTaskToast: 看板任务完成/阻塞/失败的 toast 与系统通知，操作与点击直达该状态列;
 * KanbanTaskToastDeps: 所需的翻译、路由、toast 与跨标签页通知能力
 *
 * [POS]
 * 全局事件的看板任务提示。失败不展示服务端措辞（运行记录在看板里），定时阻塞不打扰。
 */
import { blockedReasonText } from '@/lib/kanban/kanbanBlockedReason';
import { buildKanbanBoardDeepLink } from '@/lib/kanban/kanbanChatBoard';
import type { toast } from '@/lib/utils/toast';

export type KanbanTaskToastTranslator = (key: string) => string;

export interface KanbanTaskToastDeps {
  /** Translator of the `notifications` namespace (status labels, the board action). */
  t: KanbanTaskToastTranslator;
  /** Translator of the `kanban` namespace (blocked reasons). */
  tKanban: KanbanTaskToastTranslator;
  router: { push: (href: string) => void };
  pushToast: { [K in 'success' | 'warning']: (...args: Parameters<(typeof toast)[K]>) => void };
  notifyIfLeader: (title: string, body?: string, onClick?: () => void) => void;
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
 * The server sends the reason as written (`detail`) only for a task that completed or blocked; a blocked reason it
 * knows is shown in the interface language. A failed task carries none: the board holds its run history, and both the
 * toast action and the notification click open the board on that column. A scheduled block is silent: the task
 * resumes by itself and its card shows when.
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

  const { t, tKanban, router, pushToast, notifyIfLeader } = deps;
  const status = String(data.status ?? '') || action.replace('task_', '');
  if (status === 'blocked' && data.block_kind === 'scheduled') {
    return;
  }
  const label = `${t(statusLabelKey(status))}: ${title}`;
  const detail = String(data.detail ?? '');
  const description = detail ? clipDescription(blockedReasonText(detail, tKanban)) : undefined;
  const boardId = String(data.board_id ?? '');
  const openBoard = boardId ? () => router.push(buildKanbanBoardDeepLink({ boardId, status })) : undefined;
  const options = {
    description,
    dismissible: true,
    action: openBoard && { label: t('viewKanbanBoard'), onClick: openBoard },
  };

  if (status === 'completed') {
    pushToast.success(label, { ...options, duration: 8_000 });
  } else {
    pushToast.warning(label, { ...options, duration: 10_000 });
  }
  notifyIfLeader(label, description, openBoard);
}
