/**
 * [INPUT]
 * - @/components/features/app-shell/confirm-dialog (POS: 通用确认对话框)
 * - ./useKanbanMoveTask::ForcePromoteState (POS: 依赖未满足时待确认的强制晋升)
 * - ./useKanbanDnD::DropConfirmState (POS: 拖拽后待确认的批量移动)
 *
 * [OUTPUT]
 * - KanbanMoveConfirmDialogs (default): 「依赖未满足，强制晋升？」与「确认移动到该列？」两个确认框
 *
 * [POS]
 * 看板移动流程里需要用户二次确认的两个对话框；只渲染，状态与确认动作由调用方持有。
 */
'use client';

import { useTranslations } from 'next-intl';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import type { DropConfirmState } from './useKanbanDnD';
import type { ForcePromoteState } from './useKanbanMoveTask';

interface KanbanMoveConfirmDialogsProps {
  forcePromoteState: ForcePromoteState | null;
  onForcePromoteDismiss: () => void;
  onForcePromoteConfirm: () => void;
  dropConfirmState: DropConfirmState | null;
  onDropDismiss: () => void;
  onDropConfirm: () => void;
}

export default function KanbanMoveConfirmDialogs({
  forcePromoteState,
  onForcePromoteDismiss,
  onForcePromoteConfirm,
  dropConfirmState,
  onDropDismiss,
  onDropConfirm,
}: KanbanMoveConfirmDialogsProps) {
  const t = useTranslations('kanban');

  return (
    <>
      <ConfirmDialog
        open={!!forcePromoteState}
        onOpenChange={(open) => {
          if (!open) {
            onForcePromoteDismiss();
          }
        }}
        title={t('forcePromoteTitle')}
        description={
          forcePromoteState
            ? `${t('forcePromoteDesc')}\n${forcePromoteState.parentTitles.map((p) => `• ${p}`).join('\n')}`
            : ''
        }
        confirmText={t('forcePromoteConfirm')}
        cancelText={t('cancel')}
        variant="warning"
        onConfirm={onForcePromoteConfirm}
      />

      <ConfirmDialog
        open={!!dropConfirmState}
        onOpenChange={(open) => {
          if (!open) {
            onDropDismiss();
          }
        }}
        title={t('dropConfirmTitle')}
        description={
          dropConfirmState ? t('dropConfirmDesc', { status: t(`status.${dropConfirmState.targetStatus}`) }) : ''
        }
        confirmText={t('dropConfirmConfirm')}
        cancelText={t('cancel')}
        variant="destructive"
        onConfirm={onDropConfirm}
      />
    </>
  );
}
