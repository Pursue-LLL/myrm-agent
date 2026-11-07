'use client';

/**
 * [INPUT] ./batchProjectModel (POS: 进度与时间格式化), @/lib/utils/timeUtils::formatDuration (POS: 起止时间耗时), next-intl (POS: batchDirectory 文案)
 * [OUTPUT] BatchProjectOverview: 详情页的「进度概览」与「运行配置」两张并排卡片
 * [POS] 详情页的只读摘要区：任务总数 / 完成 / 失败计数、整体进度条，以及看板、并发、Agent、通知、创建 / 结束时间与耗时。
 */

import type { ReactNode } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Progress } from '@/components/primitives/progress';
import { cn } from '@/lib/utils/classnameUtils';
import { formatDuration } from '@/lib/utils/timeUtils';
import type { BatchProjectDetail } from '@/services/batch-directory';
import { batchProgressPercent, formatDateTime } from './batchProjectModel';

interface StatTileProps {
  value: number;
  label: string;
  valueClassName?: string;
}

function StatTile({ value, label, valueClassName }: StatTileProps) {
  return (
    <div className="rounded-md border p-3 text-center">
      <p className={cn('text-xl font-semibold', valueClassName)}>{value}</p>
      <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
    </div>
  );
}

interface ConfigRowProps {
  label: string;
  children: ReactNode;
  valueClassName?: string;
  testId?: string;
  valueTestId?: string;
}

function ConfigRow({ label, children, valueClassName, testId, valueTestId }: ConfigRowProps) {
  return (
    <div className="flex justify-between gap-4" data-testid={testId}>
      <span className="text-muted-foreground shrink-0">{label}</span>
      <span className={valueClassName} data-testid={valueTestId}>
        {children}
      </span>
    </div>
  );
}

export function BatchProjectOverview({ project }: { project: BatchProjectDetail }) {
  const t = useTranslations('batchDirectory');
  const total = project.total_tasks || 0;
  const done = project.completed_tasks + project.failed_tasks;
  const percent = batchProgressPercent(project);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('overviewTitle')}</CardTitle>
          <CardDescription>{t('overviewDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{t('statProgress')}</span>
            <span className="font-medium">
              {done}/{total} ({percent}%)
            </span>
          </div>
          <Progress value={percent} />
          <div className="grid grid-cols-3 gap-2 pt-1">
            <StatTile value={total} label={t('statTotalTasks')} />
            <StatTile value={project.completed_tasks} label={t('statCompleted')} valueClassName="text-emerald-500" />
            <StatTile value={project.failed_tasks} label={t('statFailed')} valueClassName="text-destructive-text" />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('configTitle')}</CardTitle>
          <CardDescription>{t('configDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <ConfigRow label={t('configBoard')} valueClassName="truncate font-mono text-xs">
            {project.board_id ? (
              <Link href="/work" className="hover:underline">
                {project.board_id}
              </Link>
            ) : (
              '—'
            )}
          </ConfigRow>
          <ConfigRow label={t('configConcurrency')} valueClassName="font-mono">
            {project.concurrency}
          </ConfigRow>
          <ConfigRow label={t('configAgent')} valueClassName="truncate font-mono text-xs">
            {project.agent_id || '—'}
          </ConfigRow>
          <ConfigRow label={t('configNotify')}>
            {project.notify_enabled ? t('configEnabled') : t('configDisabled')}
          </ConfigRow>
          <ConfigRow label={t('configCreated')} valueClassName="text-xs">
            {formatDateTime(project.created_at)}
          </ConfigRow>
          <ConfigRow label={t('configFinished')} valueClassName="text-xs">
            {formatDateTime(project.finished_at)}
          </ConfigRow>
          <ConfigRow
            label={t('configDuration')}
            valueClassName="text-xs"
            testId="bd-config-duration"
            valueTestId="bd-config-duration-value"
          >
            {formatDuration(project.started_at, project.finished_at)}
          </ConfigRow>
        </CardContent>
      </Card>
    </div>
  );
}
