'use client';

/**
 * [INPUT] @/components/features/cron/cron-utils::isFailedRunStatus, runStatusLabelKey (POS: 失败状态判定与运行状态标签), @/services/cron::RunStatus (POS: 运行状态类型)
 * [OUTPUT] HeartbeatLastRun: 心跳上次运行的时间与结果
 * [POS] 心跳设置里的「上次运行」一行：结果用定时任务的运行状态词；无内容的健康巡检以 skipped 结束，不是警示，所以只有失败着色。
 */

import { useTranslations } from 'next-intl';
import { isFailedRunStatus, runStatusLabelKey } from '@/components/features/cron/cron-utils';
import { cn } from '@/lib/utils/classnameUtils';
import type { RunStatus } from '@/services/cron';

function statusTone(status: RunStatus): string {
  if (status === 'ok') {
    return 'text-green-600 dark:text-green-400';
  }
  return isFailedRunStatus(status) ? 'text-destructive-text' : 'text-muted-foreground';
}

interface HeartbeatLastRunProps {
  at: string;
  status: RunStatus | null;
}

export default function HeartbeatLastRun({ at, status }: HeartbeatLastRunProps) {
  const t = useTranslations('heartbeat');
  const tCron = useTranslations('cron');
  return (
    <p>
      {t('lastRun')}: {new Date(at).toLocaleString()}
      {status && <span className={cn('ml-2', statusTone(status))}>({tCron(runStatusLabelKey(status))})</span>}
    </p>
  );
}
