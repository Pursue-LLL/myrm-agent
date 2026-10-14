/**
 * [INPUT]
 * - @/components/features/app-shell/confirm-dialog::ConfirmDialog (POS: 通用确认对话框)
 * - @/services/kanban::KanbanTask (POS: 看板 API 类型)
 *
 * [OUTPUT]
 * - useKanbanTaskActionConfirm: 回收 / 删除任务的待确认状态与发起函数
 * - KanbanTaskActionConfirm: 写明后果的确认对话框
 *
 * [POS]
 * 看板上两个破坏性操作的确认层：回收会立刻中断正在执行的 Agent，删除任务不可恢复且会放行等待它的下游任务。
 * 卡片菜单只发起请求，用户确认后才调用执行函数。
 */
'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import type { KanbanTask } from '@/services/kanban';

type TaskActionKind = 'reclaim' | 'delete';

export interface TaskActionConfirmState {
  kind: TaskActionKind;
  taskId: string;
  /** 发起时记下标题：确认删除后看板会刷新，任务已不在列表里，关闭动画期间文案不能变空。 */
  title: string;
  open: boolean;
}

export function useKanbanTaskActionConfirm(tasks: readonly KanbanTask[]) {
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
  // 只关闭不清空：对话框退场动画期间仍要渲染原来的标题与描述。
  const dismiss = useCallback(() => setState((prev) => (prev ? { ...prev, open: false } : prev)), []);

  return { state, requestReclaim, requestDelete, dismiss };
}

interface KanbanTaskActionConfirmProps {
  state: TaskActionConfirmState | null;
  onDismiss: () => void;
  onReclaim: (taskId: string) => Promise<void>;
  onDelete: (taskId: string) => Promise<void>;
}

export function KanbanTaskActionConfirm({ state, onDismiss, onReclaim, onDelete }: KanbanTaskActionConfirmProps) {
  const t = useTranslations('kanban');
  if (!state) {
    return null;
  }

  const isDelete = state.kind === 'delete';
  return (
    <ConfirmDialog
      open={state.open}
      onOpenChange={(open) => {
        if (!open) {
          onDismiss();
        }
      }}
      title={isDelete ? t('deleteConfirmTitle') : t('reclaimTitle')}
      description={isDelete ? t('deleteConfirmDesc', { title: state.title }) : t('reclaimDesc')}
      confirmText={isDelete ? t('deleteAction') : t('reclaimAction')}
      cancelText={t('cancel')}
      variant={isDelete ? 'destructive' : 'warning'}
      onConfirm={() => (isDelete ? onDelete(state.taskId) : onReclaim(state.taskId))}
    />
  );
}
