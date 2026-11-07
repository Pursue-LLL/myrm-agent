/**
 * [INPUT] @/services/batch-directory::listBatchProjects / cancelBatchProject / deleteBatchProject (POS: 批量项目增删查与取消), @/hooks/shared/useToast (POS: 结果提示)
 * [OUTPUT] useBatchProjects: 项目列表、加载态、取消中的项目 id、聚合统计，以及 refresh / cancel / remove 动作
 * [POS] 列表页的数据与动作层；挂载时拉取一次，每次动作成功后重新拉取，失败统一 toast 提示。
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/hooks/shared/useToast';
import {
  cancelBatchProject,
  deleteBatchProject,
  listBatchProjects,
  type BatchProject,
} from '@/services/batch-directory';

export interface BatchProjectsSummary {
  projectCount: number;
  running: number;
  completed: number;
  failed: number;
}

export function useBatchProjects() {
  const t = useTranslations('batchDirectory');
  const [projects, setProjects] = useState<BatchProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const items = await listBatchProjects();
      setProjects(items);
    } catch {
      toast.error(t('listError'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const cancel = useCallback(
    async (p: BatchProject) => {
      setCancellingId(p.project_id);
      try {
        await cancelBatchProject(p.project_id);
        toast.success(t('cancelSuccess', { name: p.name }));
        await refresh();
      } catch {
        toast.error(t('cancelError'));
      } finally {
        setCancellingId(null);
      }
    },
    [refresh, t],
  );

  const remove = useCallback(
    async (p: BatchProject) => {
      try {
        await deleteBatchProject(p.project_id);
        toast.success(t('deleteSuccess', { name: p.name }));
        await refresh();
      } catch {
        toast.error(t('deleteError'));
      }
    },
    [refresh, t],
  );

  const summary = useMemo<BatchProjectsSummary>(
    () => ({
      projectCount: projects.length,
      running: projects.filter((p) => p.status === 'running').length,
      completed: projects.reduce((acc, p) => acc + p.completed_tasks, 0),
      failed: projects.reduce((acc, p) => acc + p.failed_tasks, 0),
    }),
    [projects],
  );

  return { projects, loading, cancellingId, summary, refresh, cancel, remove };
}
