/**
 * [INPUT]
 * - @/components/primitives/dropdown-menu (POS: Radix 下拉菜单封装)
 * - @/lib/utils/a11y::REVEAL_ON_HOVER (POS: 悬停 / 聚焦 / 触屏三路径揭示契约)
 * - ./kanban-styles::NEXT_STATUSES (POS: 各状态可流转的目标状态)
 * - ./kanban-transitions::moveLabelKey (POS: 状态流转入口文案)
 *
 * [OUTPUT]
 * - KanbanTaskCardActions: 任务卡片的单一操作菜单（详情 / Specify / Decompose / 状态流转 / 回收 / 删除）
 *
 * [POS]
 * 看板卡片操作入口。触发器常驻 DOM：桌面悬停或键盘聚焦时显现，触屏常显，因此键盘与触屏用户都能到达这些操作。
 */
'use client';

import type { SyntheticEvent } from 'react';
import { DotsThree } from '@phosphor-icons/react';
import { useTranslations } from 'next-intl';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/primitives/dropdown-menu';
import { REVEAL_ON_HOVER } from '@/lib/utils/a11y';
import { cn } from '@/lib/utils/classnameUtils';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import { NEXT_STATUSES } from './kanban-styles';
import { moveLabelKey } from './kanban-transitions';

interface KanbanTaskCardActionsProps {
  task: KanbanTask;
  onMove: (taskId: string, status: TaskStatus) => void;
  onDelete: (taskId: string) => void;
  onReclaim?: (taskId: string) => void;
  onOpenTaskDrawer?: (taskId: string) => void;
  onSpecify: () => void;
  onDecompose: () => void;
}

const stopPropagation = (event: SyntheticEvent) => event.stopPropagation();

/**
 * 卡片外层是 dnd-kit 的拖拽源并监听点击 / 双击，菜单触发器与（经 portal 冒泡回来的）菜单内容
 * 上的指针手势不能再交给卡片：否则按下触发器会起拖拽、双击会打开详情抽屉。
 */
const ISOLATE_FROM_CARD = {
  onPointerDown: stopPropagation,
  onClick: stopPropagation,
  onDoubleClick: stopPropagation,
} as const;

const ITEM_CLASS = 'pointer-coarse:min-h-11';

export default function KanbanTaskCardActions({
  task,
  onMove,
  onDelete,
  onReclaim,
  onOpenTaskDrawer,
  onSpecify,
  onDecompose,
}: KanbanTaskCardActionsProps) {
  const t = useTranslations('kanban');

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          data-testid={`kanban-task-actions-${task.task_id}`}
          aria-label={t('cardActions')}
          className={cn(
            'inline-flex size-6 shrink-0 items-center justify-center rounded text-muted-foreground transition-opacity',
            'hover:bg-muted pointer-coarse:size-8',
            REVEAL_ON_HOVER,
          )}
          {...ISOLATE_FROM_CARD}
        >
          <DotsThree size={16} weight="bold" aria-hidden />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" {...ISOLATE_FROM_CARD}>
        {onOpenTaskDrawer && (
          <DropdownMenuItem className={ITEM_CLASS} onSelect={() => onOpenTaskDrawer(task.task_id)}>
            {t('taskDetails')}
          </DropdownMenuItem>
        )}
        {task.status === 'triage' && (
          <>
            <DropdownMenuItem className={ITEM_CLASS} title={t('specifyHint')} onSelect={onSpecify}>
              {t('specify')}
            </DropdownMenuItem>
            <DropdownMenuItem className={ITEM_CLASS} title={t('decomposeHint')} onSelect={onDecompose}>
              {t('decompose')}
            </DropdownMenuItem>
          </>
        )}
        {NEXT_STATUSES[task.status]?.map((nextStatus) => (
          <DropdownMenuItem key={nextStatus} className={ITEM_CLASS} onSelect={() => onMove(task.task_id, nextStatus)}>
            {t(moveLabelKey(task.status, nextStatus))}
          </DropdownMenuItem>
        ))}
        {task.status === 'running' && onReclaim && (
          <DropdownMenuItem
            className={cn(ITEM_CLASS, 'text-destructive focus:text-destructive')}
            onSelect={() => onReclaim(task.task_id)}
          >
            {t('reclaimAction')}
          </DropdownMenuItem>
        )}
        <DropdownMenuItem
          className={cn(ITEM_CLASS, 'text-destructive focus:text-destructive')}
          onSelect={() => onDelete(task.task_id)}
        >
          {t('deleteAction')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
