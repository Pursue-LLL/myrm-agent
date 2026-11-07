'use client';

/**
 * [INPUT] @/services/cron::CronJob (POS: Cron 任务 DTO)
 * [OUTPUT] CronJobCardActions: 卡片右侧的立即运行、复制、暂停/恢复与删除按钮；点击不冒泡到卡片选中
 * [POS] CronJobCard 的操作区，纯展示，动作由 useCronJobActions 与父组件的删除回调提供。
 */

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { Pause, Play, Trash2, RotateCw, Copy } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import { cn } from '@/lib/utils/classnameUtils';
import type { CronJob } from '@/services/cron';

interface CronJobCardActionsProps {
  job: CronJob;
  triggering: boolean;
  duplicating: boolean;
  canResume: boolean;
  onTrigger: () => void;
  onDuplicate: () => void;
  onToggle: () => void;
  onRequestDelete: (job: CronJob) => void;
}

export const CronJobCardActions = memo(
  ({
    job,
    triggering,
    duplicating,
    canResume,
    onTrigger,
    onDuplicate,
    onToggle,
    onRequestDelete,
  }: CronJobCardActionsProps) => {
    const t = useTranslations('cron');

    return (
      <div role="presentation" className="flex items-center gap-0.5 shrink-0" onClick={(e) => e.stopPropagation()}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="icon"
              variant="ghost"
              className="h-7 w-7"
              onClick={onTrigger}
              disabled={job.status !== 'active' || triggering}
            >
              <RotateCw className={cn('h-3.5 w-3.5', triggering && 'animate-spin')} />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t('trigger')}</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={onDuplicate} disabled={duplicating}>
              <Copy className="h-3.5 w-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t('duplicate')}</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="icon"
              variant="ghost"
              className="h-7 w-7"
              onClick={onToggle}
              disabled={job.status !== 'active' && !canResume}
            >
              {job.status === 'active' ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {job.status === 'active' ? t('pause') : canResume ? t('resume') : t('resumeBlocked')}
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="icon"
              variant="ghost"
              className="h-7 w-7 text-destructive-text hover:text-destructive-text"
              onClick={() => onRequestDelete(job)}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t('delete')}</TooltipContent>
        </Tooltip>
      </div>
    );
  },
);
CronJobCardActions.displayName = 'CronJobCardActions';
