/**
 * [INPUT]
 * - @/lib/kanban/kanbanBlockedReason::blockedReasonText (POS: 阻塞原因的界面语言文案)
 * - @/services/kanban::KanbanTask (POS: block_kind / blocked_reason / scheduled_until 字段)
 *
 * [OUTPUT]
 * - KanbanTaskBlockedNotice: 任务抽屉里的阻塞提示条——阻塞类型标签（`kanban.blockKind.*`，没有类型时用 `kanban.status.blocked`）、界面语言的原因，定时阻塞时附自动解除时间
 *
 * [POS]
 * 任务抽屉详情区段的阻塞展示；没有 blocked_reason 时不渲染。
 */
import { Clock, ExternalLink, User } from 'lucide-react';
import { blockedReasonText } from '@/lib/kanban/kanbanBlockedReason';
import type { KanbanTask } from '@/services/kanban';

interface KanbanTaskBlockedNoticeProps {
  task: KanbanTask;
  /** Translator of the `kanban` namespace. */
  t: (key: string) => string;
}

export function KanbanTaskBlockedNotice({ task, t }: KanbanTaskBlockedNoticeProps) {
  if (!task.blocked_reason) {
    return null;
  }

  return (
    <div className="text-xs text-destructive bg-destructive/5 rounded px-2 py-1 mt-1 space-y-0.5">
      <p className="flex items-center gap-1">
        {task.block_kind === 'scheduled' && <Clock className="w-3.5 h-3.5 shrink-0" />}
        {task.block_kind === 'external' && <ExternalLink className="w-3.5 h-3.5 shrink-0" />}
        {task.block_kind === 'human' && <User className="w-3.5 h-3.5 shrink-0" />}
        <span className="font-medium">{task.block_kind ? t(`blockKind.${task.block_kind}`) : t('status.blocked')}</span>
        <span className="text-muted-foreground">—</span>
        {blockedReasonText(task.blocked_reason, t)}
      </p>
      {task.block_kind === 'scheduled' && task.scheduled_until && (
        <p className="text-[10px] text-chart-4 font-mono">
          {t('autoUnblockAt')}: {new Date(task.scheduled_until).toLocaleString()}
        </p>
      )}
    </div>
  );
}
