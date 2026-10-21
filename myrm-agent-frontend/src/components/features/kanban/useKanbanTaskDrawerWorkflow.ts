/**
 * [INPUT]
 * - @/services/kanban::moveTask, promoteTask, reclaimTask, approveTask, rejectTask (POS: 任务状态流转 API)
 * - @/services/riskHeldToast::isRiskHeldError (POS: 被风控规则拦下的文字已有统一提示，失败提示据此跳过)
 * - ./kanban-transitions::resolveMoveIntent (POS: 判断移动是否属于重试或归档)
 *
 * [OUTPUT]
 * - useKanbanTaskDrawerWorkflow: 抽屉里的状态流转动作：审批通过 / 驳回（驳回需理由）、移动、强制提升、回收（可带理由并改派 Agent）
 *
 * [POS]
 * useKanbanTaskDrawer 的流转子 hook。重试与归档交回看板统一的确认流程；backlog -> ready 先做依赖检查，未满足时给出强制提升的选择。
 */
import { useCallback, useState } from 'react';
import { toast } from 'sonner';
import type { KanbanTask, TaskStatus, PromoteResult } from '@/services/kanban';
import { moveTask, promoteTask, reclaimTask, approveTask, rejectTask } from '@/services/kanban';
import { isRiskHeldError } from '@/services/riskHeldToast';
import { resolveMoveIntent } from './kanban-transitions';

interface UseKanbanTaskDrawerWorkflowParams {
  task: KanbanTask | null;
  onRefresh: () => void;
  onOpenChange: (open: boolean) => void;
  /** 重试与归档需要二次确认，交给看板统一的确认流程。 */
  onRequestMove: (taskId: string, targetStatus: TaskStatus) => void;
  t: (key: string) => string;
}

export function useKanbanTaskDrawerWorkflow({
  task,
  onRefresh,
  onOpenChange,
  onRequestMove,
  t,
}: UseKanbanTaskDrawerWorkflowParams) {
  const [promoteConfirm, setPromoteConfirm] = useState<PromoteResult | null>(null);
  const [promoting, setPromoting] = useState(false);
  const [showReclaimDialog, setShowReclaimDialog] = useState(false);
  const [reclaimReason, setReclaimReason] = useState('');
  const [reclaimAgentId, setReclaimAgentId] = useState('');
  const [reclaiming, setReclaiming] = useState(false);
  const [showRejectDialog, setShowRejectDialog] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [approving, setApproving] = useState(false);
  const [rejecting, setRejecting] = useState(false);

  const handleApprove = useCallback(async () => {
    if (!task) {
      return;
    }
    setApproving(true);
    try {
      await approveTask(task.task_id);
      onRefresh();
      onOpenChange(false);
      toast.success(t('approveSuccess'));
    } catch {
      toast.error(t('approveError'));
    }
    setApproving(false);
  }, [task, onRefresh, onOpenChange, t]);

  const handleReject = useCallback(async () => {
    if (!task) {
      return;
    }
    if (!rejectReason.trim()) {
      toast.error(t('rejectReasonRequired'));
      return;
    }
    setRejecting(true);
    try {
      await rejectTask(task.task_id, rejectReason.trim());
      setShowRejectDialog(false);
      setRejectReason('');
      onRefresh();
      onOpenChange(false);
      toast.success(t('rejectSuccess'));
    } catch (error) {
      // `apiRequest` has already shown the notice for a held reason; the dialog keeps the text.
      if (!isRiskHeldError(error)) {
        toast.error(t('rejectError'));
      }
    }
    setRejecting(false);
  }, [task, rejectReason, onRefresh, onOpenChange, t]);

  const handleMove = useCallback(
    async (targetStatus: TaskStatus) => {
      if (!task) {
        return;
      }
      const intent = resolveMoveIntent(task.status, targetStatus);
      if (intent === 'retry' || intent === 'archive') {
        onOpenChange(false);
        onRequestMove(task.task_id, targetStatus);
        return;
      }
      if (task.status === 'backlog' && targetStatus === 'ready') {
        setPromoting(true);
        try {
          const result = await promoteTask(task.task_id, false);
          if (result.promoted) {
            onRefresh();
            onOpenChange(false);
            toast.success(t('promoteSuccess'));
          } else {
            setPromoteConfirm(result);
          }
        } catch {
          toast.error(t('promoteError'));
        }
        setPromoting(false);
        return;
      }
      try {
        await moveTask(task.task_id, targetStatus);
        onRefresh();
        onOpenChange(false);
      } catch {
        toast.error(t('moveError'));
      }
    },
    [task, onRefresh, onOpenChange, onRequestMove, t],
  );

  const handleForcePromote = useCallback(async () => {
    if (!task) {
      return;
    }
    setPromoting(true);
    try {
      const result = await promoteTask(task.task_id, true);
      if (result.promoted) {
        setPromoteConfirm(null);
        onRefresh();
        onOpenChange(false);
        toast.success(t('promoteSuccess'));
      }
    } catch {
      toast.error(t('promoteError'));
    }
    setPromoting(false);
  }, [task, onRefresh, onOpenChange, t]);

  const handleReclaim = useCallback(async () => {
    if (!task) {
      return;
    }
    setReclaiming(true);
    try {
      const result = await reclaimTask(task.task_id, reclaimReason || undefined, reclaimAgentId || undefined);
      if (result.reclaimed) {
        setShowReclaimDialog(false);
        setReclaimReason('');
        setReclaimAgentId('');
        onRefresh();
        toast.success(t('reclaimSuccess'));
      }
    } catch (error) {
      // `apiRequest` has already shown the notice for a held reason; the dialog keeps the text.
      if (!isRiskHeldError(error)) {
        toast.error(t('reclaimFailed'));
      }
    }
    setReclaiming(false);
  }, [task, reclaimReason, reclaimAgentId, onRefresh, t]);

  return {
    promoteConfirm,
    setPromoteConfirm,
    promoting,
    showReclaimDialog,
    setShowReclaimDialog,
    reclaimReason,
    setReclaimReason,
    reclaimAgentId,
    setReclaimAgentId,
    reclaiming,
    showRejectDialog,
    setShowRejectDialog,
    rejectReason,
    setRejectReason,
    approving,
    rejecting,
    handleMove,
    handleForcePromote,
    handleReclaim,
    handleApprove,
    handleReject,
  };
}
