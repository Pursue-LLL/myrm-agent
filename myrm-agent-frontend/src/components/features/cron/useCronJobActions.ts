/**
 * [INPUT] @/store/useCronStore (POS: 暂停/恢复/触发/刷新), @/services/cron::duplicateCronJob (POS: 复制任务)
 * [OUTPUT] useCronJobActions: 任务卡片的暂停/恢复切换、立即运行（5 秒防连点）、复制及 canResume 判定，失败统一 toast 提示
 * [POS] CronJobCard 的动作层。
 */

import { useCallback, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';
import { toast } from 'sonner';
import { duplicateCronJob, type CronJob } from '@/services/cron';
import useCronStore from '@/store/useCronStore';

export function useCronJobActions(job: CronJob) {
  const t = useTranslations('cron');
  const { pauseJob, resumeJob, triggerJob, fetchJobs } = useCronStore(
    useShallow((s) => ({
      pauseJob: s.pauseJob,
      resumeJob: s.resumeJob,
      triggerJob: s.triggerJob,
      fetchJobs: s.fetchJobs,
    })),
  );

  const canResume = useMemo(() => {
    if (job.status === 'active') {
      return true;
    }
    if (job.status === 'completed') {
      return false;
    }
    if (job.expires_at && new Date(job.expires_at).getTime() <= Date.now()) {
      return false;
    }
    if (job.max_fires !== null && job.max_fires !== undefined && job.fire_count >= job.max_fires) {
      return false;
    }
    return true;
  }, [job.status, job.expires_at, job.max_fires, job.fire_count]);

  const handleToggle = useCallback(async () => {
    try {
      if (job.status === 'active') {
        await pauseJob(job.id);
        toast.success(t('pauseSuccess', { name: job.name }));
      } else {
        await resumeJob(job.id);
        toast.success(t('resumeSuccess', { name: job.name }));
      }
    } catch {
      toast.error(t('actionFail'));
    }
  }, [job, pauseJob, resumeJob, t]);

  const [triggering, setTriggering] = useState(false);

  const handleTrigger = useCallback(async () => {
    if (triggering) {
      return;
    }
    setTriggering(true);
    try {
      await triggerJob(job.id);
      toast.success(t('triggerSuccess', { name: job.name }));
    } catch {
      toast.error(t('triggerFail'));
      setTriggering(false);
      return;
    }
    setTimeout(() => setTriggering(false), 5_000);
  }, [triggering, job, triggerJob, t]);

  const [duplicating, setDuplicating] = useState(false);

  const handleDuplicate = useCallback(async () => {
    if (duplicating) {
      return;
    }
    setDuplicating(true);
    try {
      await duplicateCronJob(job.id);
      toast.success(t('duplicateSuccess', { name: job.name }));
      fetchJobs(true);
    } catch {
      toast.error(t('duplicateFail'));
    } finally {
      setDuplicating(false);
    }
  }, [duplicating, job, fetchJobs, t]);

  return { canResume, triggering, duplicating, handleToggle, handleTrigger, handleDuplicate };
}
