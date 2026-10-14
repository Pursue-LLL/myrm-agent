/**
 * [INPUT]
 * - @/components/features/app-shell/confirm-dialog::ConfirmDialog (POS: 通用确认对话框)
 * - ./kanban-transitions::resolveMoveIntent (POS: 看板状态流转判定)
 * - @/services/kanban::KanbanTask, TaskStatus (POS: 看板 API 类型)
 *
 * [OUTPUT]
 * - useKanbanTaskActionConfirm: 回收 / 删除 / 重试 / 归档任务的待确认状态与发起函数，以及按流转含义分流的 requestMove
 * - KanbanTaskActionConfirm: 写明后果的确认对话框
 *
 * [POS]
 * 看板上需要二次确认的任务操作：回收会立刻中断正在执行的 Agent，删除不可恢复且会放行下游任务，
 * 重试会再次消耗模型额度，归档后任务离开看板且无法在界面恢复。
 * 卡片菜单、抽屉、拖拽只发起请求，用户确认后才调用执行函数。
 */
'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import type { KanbanTask, TaskStatus } from '@/services/kanban';
import { resolveMoveIntent } from './kanban-transitions';

type TaskActionKind = 'reclaim' | 'delete' | 'retry' | 'archive';

export interface TaskActionConfirmState {
  kind: TaskActionKind;
  taskId: string;
  /** 发起时记下标题：确认删除后看板会刷新，任务已不在列表里，关闭动画期间文案不能变空。 */
  title: string;
  open: boolean;
}

export function useKanbanTaskActionConfirm(
  tasks: readonly KanbanTask[],
  onMove: (taskId: string, status: TaskStatus) => void,
) {
  const [state, setState] = useState<TaskActionConfirmState | null>(null);

  const request = useCallback(
    (kind: TaskActionKind, taskId: string) => {
      const title = tasks.find((task) => task.task_id === taskId)?.title ?? '';
      setState({ kind, taskId, title, open: true });
    },
    [tasks],
  );
  const requestReclaim = useCallback((taskId: string) => request('reclaim', taskId), [request]);
  const requestDelete = useCallback((taskId: string) => request('delete', taskId), [request]);
  /** 状态流转的统一入口：失败 → 就绪是重试，归档先确认，其余直接流转。 */
  const requestMove = useCallback(
    (taskId: string, status: TaskStatus) => {
      const current = tasks.find((task) => task.task_id === taskId)?.status;
      const intent = current ? resolveMoveIntent(current, status) : 'move';
      if (intent === 'retry' || intent === 'archive') {
        request(intent, taskId);
      } else {
        onMove(taskId, status);
      }
    },
    [tasks, request, onMove],
  );
  // 只关闭不清空：对话框退场动画期间仍要渲染原来的标题与描述。
  const dismiss = useCallback(() => setState((prev) => (prev ? { ...prev, open: false } : prev)), []);

  return { state, requestReclaim, requestDelete, requestMove, dismiss };
}

interface KanbanTaskActionConfirmProps {
  state: TaskActionConfirmState | null;
  onDismiss: () => void;
  onReclaim: (taskId: string) => Promise<void>;
  onDelete: (taskId: string) => Promise<void>;
  onRetry: (taskId: string) => Promise<void>;
  onArchive: (taskId: string) => Promise<void>;
}

export function KanbanTaskActionConfirm({
  state,
  onDismiss,
  onReclaim,
  onDelete,
  onRetry,
  onArchive,
}: KanbanTaskActionConfirmProps) {
  const t = useTranslations('kanban');
  if (!state) {
    return null;
  }

  const copy = (() => {
    switch (state.kind) {
      case 'delete':
        return {
          variant: 'destructive',
          title: t('deleteConfirmTitle'),
          description: t('deleteConfirmDesc', { title: state.title }),
          confirmText: t('deleteAction'),
          run: onDelete,
        } as const;
      case 'retry':
        return {
          variant: 'info',
          title: t('retryTitle'),
          description: t('retryDesc'),
          confirmText: t('retryAction'),
          run: onRetry,
        } as const;
      case 'archive':
        return {
          variant: 'warning',
          title: t('archiveConfirmTitle'),
          description: t('archiveConfirmDesc', { title: state.title }),
          confirmText: t('moveTo.archived'),
          run: onArchive,
        } as const;
      case 'reclaim':
        return {
          variant: 'warning',
          title: t('reclaimTitle'),
          description: t('reclaimDesc'),
          confirmText: t('reclaimAction'),
          run: onReclaim,
        } as const;
    }
  })();

  return (
    <ConfirmDialog
      open={state.open}
      onOpenChange={(open) => {
        if (!open) {
          onDismiss();
        }
      }}
      title={copy.title}
      description={copy.description}
      confirmText={copy.confirmText}
      cancelText={t('cancel')}
      variant={copy.variant}
      onConfirm={() => copy.run(state.taskId)}
    />
  );
}
