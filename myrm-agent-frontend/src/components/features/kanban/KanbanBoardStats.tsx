/**
 * [INPUT]
 * - ./kanban-styles::STATUS_COLUMNS (POS: 看板列顺序)
 * - @/services/kanban::BoardSummary (POS: 看板汇总数据类型)
 *
 * [OUTPUT]
 * - KanbanBoardStats (default): 各状态计数条、等待过久 / 疑似卡死提示，以及按 Agent 的任务分布
 *
 * [POS]
 * 看板主视图的汇总展示；Running 计数带并发上限，Agent 分布只在出现多个负责人时显示。
 */
'use client';

import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { BoardSummary, TaskStatus } from '@/services/kanban';
import { STATUS_COLUMNS } from './kanban-styles';

const STATUS_DOT_COLORS: Record<TaskStatus, string> = {
  triage: 'bg-purple-500',
  backlog: 'bg-muted-foreground/50',
  ready: 'bg-primary',
  running: 'bg-chart-4',
  blocked: 'bg-destructive',
  in_review: 'bg-amber-500',
  completed: 'bg-chart-2',
  failed: 'bg-destructive',
  archived: 'bg-muted-foreground/30',
};

interface KanbanBoardStatsProps {
  summaryData: BoardSummary | null;
  summary: Partial<Record<string, number>>;
  concurrencyLimit: number;
  agentNameMap: Map<string, string>;
}

export default function KanbanBoardStats({
  summaryData,
  summary,
  concurrencyLimit,
  agentNameMap,
}: KanbanBoardStatsProps) {
  const t = useTranslations('kanban');

  return (
    <>
      {/* Stats bar */}
      <div className="flex gap-3 text-xs text-muted-foreground flex-wrap">
        {STATUS_COLUMNS.map((status) => (
          <span key={status} className="flex items-center gap-1">
            <span className={cn('w-1.5 h-1.5 rounded-full', STATUS_DOT_COLORS[status])} />
            {status === 'running'
              ? concurrencyLimit > 0
                ? t('status.runningWithLimit', {
                    count: summary[status] || 0,
                    limit: concurrencyLimit,
                  })
                : `${t('status.running')}: ${summary[status] || 0}`
              : `${t(`status.${status}`)}: ${summary[status] || 0}`}
          </span>
        ))}
        {summaryData?.oldest_ready_age_seconds != null && summaryData.oldest_ready_age_seconds >= 300 && (
          <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400 font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
            {t('oldestReadyAge', { minutes: Math.floor(summaryData.oldest_ready_age_seconds / 60) })}
          </span>
        )}
        {(summaryData?.stale_running_count ?? 0) > 0 && (
          <span className="flex items-center gap-1 text-red-600 dark:text-red-400 font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
            {t('staleRunningCount', { count: summaryData?.stale_running_count ?? 0 })}
          </span>
        )}
      </div>

      {/* Per-agent distribution */}
      {summaryData && summaryData.by_agent.length > 1 && (
        <div className="flex gap-2 text-[10px] text-muted-foreground flex-wrap items-center">
          <span className="font-medium">{t('agentDistribution')}:</span>
          {summaryData.by_agent.map((ag) => (
            <span
              key={ag.agent_id ?? '__unassigned__'}
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-muted/50"
            >
              <span className="max-w-[100px] truncate">
                {ag.agent_id ? (agentNameMap.get(ag.agent_id) ?? ag.agent_id) : t('unassigned')}
              </span>
              <span className="text-foreground font-medium">{ag.total}</span>
            </span>
          ))}
        </div>
      )}
    </>
  );
}
