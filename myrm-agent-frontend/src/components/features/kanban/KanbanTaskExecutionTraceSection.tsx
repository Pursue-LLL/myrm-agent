/**
 * [INPUT]
 * - @/components/features/settings/sections/system/ExecutionTraceTimeline (POS: 执行轨迹时间线)
 *
 * [OUTPUT]
 * - KanbanTaskExecutionTraceSection (default): 可折叠的任务执行轨迹，展开后才加载
 *
 * [POS]
 * 任务抽屉里的执行轨迹区段：以 task_id 作 sessionId，不显示「保存为评测用例」入口；任务运行中每 30 秒刷新一次。
 */
'use client';

import { memo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import ExecutionTraceTimeline from '@/components/features/settings/sections/system/ExecutionTraceTimeline';

interface KanbanTaskExecutionTraceSectionProps {
  taskId: string;
  /**
   * When the task is running, poll the trace so the drawer live-updates while
   * the execution is still appending events.
   */
  taskStatus?: string;
}

const KanbanTaskExecutionTraceSection = memo<KanbanTaskExecutionTraceSectionProps>(({ taskId, taskStatus }) => {
  const t = useTranslations('kanban');
  const [expanded, setExpanded] = useState(false);

  return (
    <section className="rounded-lg border border-border overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-muted/40 transition-colors"
        aria-expanded={expanded}
      >
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {t('executionTrace')}
        </span>
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        )}
      </button>
      {expanded && (
        <div className={cn('border-t border-border px-2 py-2 max-h-[420px] overflow-y-auto')}>
          <ExecutionTraceTimeline
            sessionId={taskId}
            showEvalCase={false}
            pollMs={taskStatus === 'running' ? 30_000 : undefined}
          />
        </div>
      )}
    </section>
  );
});

KanbanTaskExecutionTraceSection.displayName = 'KanbanTaskExecutionTraceSection';

export default KanbanTaskExecutionTraceSection;
