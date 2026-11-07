/**
 * [INPUT] @/services/batch-directory (POS: 取消 / 重试 / 重跑 / 暂停 / 恢复 / 全部通过 / 单任务重试 / 删除 API), @/hooks/shared/useToast (POS: 结果提示)
 * [OUTPUT] useBatchProjectActions: 项目级动作 run(key)、单任务重试 retryTask、删除 remove，以及各动作相互独立的忙碌标志
 * [POS] 详情页的动作层；动作成功后 toast 并等待详情刷新完成，失败统一 toast 提示；删除成功后返回列表页。
 */

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { toast } from '@/hooks/shared/useToast';
import {
  approveAllBatchResults,
  cancelBatchProject,
  deleteBatchProject,
  pauseBatchProject,
  rerunBatchProject,
  resumeBatchProject,
  retryBatchProject,
  retryBatchTask,
  type BatchProjectDetail,
} from '@/services/batch-directory';

export type BatchActionKey = 'cancel' | 'retry' | 'rerun' | 'pause' | 'resume' | 'approveAll';

interface BatchActionSpec {
  call: (projectId: string) => Promise<BatchProjectDetail>;
  successKey: string;
  errorKey: string;
  successValues: (updated: BatchProjectDetail, projectName: string) => { name: string } | { count: number };
}

const countOf = (ids: string[] | undefined) => ({ count: ids?.length ?? 0 });

const ACTIONS: Record<BatchActionKey, BatchActionSpec> = {
  cancel: {
    call: cancelBatchProject,
    successKey: 'cancelSuccess',
    errorKey: 'cancelError',
    successValues: (_updated, name) => ({ name }),
  },
  retry: {
    call: retryBatchProject,
    successKey: 'retrySuccess',
    errorKey: 'retryError',
    successValues: (updated) => countOf(updated.retried_task_ids),
  },
  rerun: {
    call: rerunBatchProject,
    successKey: 'rerunSuccess',
    errorKey: 'rerunError',
    successValues: (updated) => countOf(updated.rerun_task_ids),
  },
  pause: {
    call: pauseBatchProject,
    successKey: 'pauseSuccess',
    errorKey: 'pauseError',
    successValues: (updated) => countOf(updated.paused_task_ids),
  },
  resume: {
    call: resumeBatchProject,
    successKey: 'resumeSuccess',
    errorKey: 'resumeError',
    successValues: (updated) => countOf(updated.resumed_task_ids),
  },
  approveAll: {
    call: approveAllBatchResults,
    successKey: 'approveAllSuccess',
    errorKey: 'approveAllError',
    successValues: (updated) => countOf(updated.approved_task_ids),
  },
};

const IDLE: Record<BatchActionKey, boolean> = {
  cancel: false,
  retry: false,
  rerun: false,
  pause: false,
  resume: false,
  approveAll: false,
};

interface UseBatchProjectActionsParams {
  projectId: string | null;
  projectName: string;
  refresh: () => Promise<void>;
}

export function useBatchProjectActions({ projectId, projectName, refresh }: UseBatchProjectActionsParams) {
  const t = useTranslations('batchDirectory');
  const router = useRouter();
  const [busy, setBusy] = useState(IDLE);
  const [retryingTaskId, setRetryingTaskId] = useState<string | null>(null);

  const run = useCallback(
    async (key: BatchActionKey) => {
      if (!projectId) {
        return;
      }
      const spec = ACTIONS[key];
      setBusy((prev) => ({ ...prev, [key]: true }));
      try {
        const updated = await spec.call(projectId);
        toast.success(t(spec.successKey, spec.successValues(updated, projectName)));
        await refresh();
      } catch {
        toast.error(t(spec.errorKey));
      } finally {
        setBusy((prev) => ({ ...prev, [key]: false }));
      }
    },
    [projectId, projectName, refresh, t],
  );

  const retryTask = useCallback(
    async (taskId: string) => {
      if (!projectId) {
        return;
      }
      setRetryingTaskId(taskId);
      try {
        const updated = await retryBatchTask(projectId, taskId);
        toast.success(t('retryTaskSuccess', countOf(updated.retried_task_ids)));
        await refresh();
      } catch {
        toast.error(t('retryTaskError'));
      } finally {
        setRetryingTaskId(null);
      }
    },
    [projectId, refresh, t],
  );

  const remove = useCallback(async () => {
    if (!projectId) {
      return;
    }
    try {
      await deleteBatchProject(projectId);
      toast.success(t('deleteSuccess', { name: projectName }));
      router.push('/batch-directories');
    } catch {
      toast.error(t('deleteError'));
    }
  }, [projectId, projectName, router, t]);

  return { busy, retryingTaskId, run, retryTask, remove };
}

export type BatchProjectActions = ReturnType<typeof useBatchProjectActions>;
