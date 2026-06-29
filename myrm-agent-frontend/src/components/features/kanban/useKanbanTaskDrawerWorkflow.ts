import { useCallback, useState } from 'react';
import { toast } from 'sonner';
import type { KanbanTask, TaskStatus, PromoteResult } from '@/services/kanban';
import { moveTask, promoteTask, reclaimTask } from '@/services/kanban';

interface UseKanbanTaskDrawerWorkflowParams {
  task: KanbanTask | null;
  onRefresh: () => void;
  onOpenChange: (open: boolean) => void;
  t: (key: string) => string;
}

export function useKanbanTaskDrawerWorkflow({
  task,
  onRefresh,
  onOpenChange,
  t,
}: UseKanbanTaskDrawerWorkflowParams) {
  const [promoteConfirm, setPromoteConfirm] = useState<PromoteResult | null>(null);
  const [promoting, setPromoting] = useState(false);
  const [showReclaimDialog, setShowReclaimDialog] = useState(false);
  const [reclaimReason, setReclaimReason] = useState('');
  const [reclaimAgentId, setReclaimAgentId] = useState('');
  const [reclaiming, setReclaiming] = useState(false);

  const handleMove = useCallback(
    async (targetStatus: TaskStatus) => {
      if (!task) return;
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
    [task, onRefresh, onOpenChange, t],
  );

  const handleForcePromote = useCallback(async () => {
    if (!task) return;
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
    if (!task) return;
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
    } catch {
      toast.error(t('reclaimFailed'));
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
    handleMove,
    handleForcePromote,
    handleReclaim,
  };
}
