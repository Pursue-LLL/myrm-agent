/**
 * [INPUT] @/services/batch-directory::getBatchProject / isBatchTerminalStatus (POS: 项目详情与终态判定), @/hooks/shared/useToast (POS: 加载失败提示)
 * [OUTPUT] useBatchProjectDetail: 解析路由 projectId，加载项目详情，非终态时每 10 秒自动刷新；返回 projectId / project / loading / refresh
 * [POS] 详情页的数据层；refresh 返回的 Promise 在拉取完成后 resolve，动作层据此保持「刷新完成前仍显示忙碌」。
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/hooks/shared/useToast';
import { getBatchProject, isBatchTerminalStatus, type BatchProjectDetail } from '@/services/batch-directory';

const AUTO_REFRESH_INTERVAL_MS = 10_000;

export function useBatchProjectDetail(params: Promise<{ projectId: string }>) {
  const t = useTranslations('batchDirectory');
  const [projectId, setProjectId] = useState<string | null>(null);
  const [project, setProject] = useState<BatchProjectDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    void params.then((p) => {
      if (active) {
        setProjectId(p.projectId);
      }
    });
    return () => {
      active = false;
    };
  }, [params]);

  const fetchDetail = useCallback(
    async (id: string) => {
      try {
        const detail = await getBatchProject(id);
        setProject(detail);
      } catch {
        toast.error(t('detailLoadError'));
      } finally {
        setLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    if (projectId) {
      void fetchDetail(projectId);
    }
  }, [projectId, fetchDetail]);

  useEffect(() => {
    if (!projectId || !project || isBatchTerminalStatus(project.status)) {
      return;
    }
    const timer = window.setInterval(() => {
      void fetchDetail(projectId);
    }, AUTO_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [projectId, project, fetchDetail]);

  const refresh = useCallback(async () => {
    if (projectId) {
      await fetchDetail(projectId);
    }
  }, [projectId, fetchDetail]);

  return { projectId, project, loading, refresh };
}
