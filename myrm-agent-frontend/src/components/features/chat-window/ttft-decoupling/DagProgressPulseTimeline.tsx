import React from 'react';
import {
  Activity,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  GitBranch,
  XCircle,
  Zap,
} from 'lucide-react';
import {
  analyzeCriticalPathProgress,
  formatElapsedMs,
  groupStepsByParallelBatch,
} from './ttftDecouplingEngine';
import { DagStepNode, DagTimelineState } from './ttftDecouplingTypes';
import { useTtftDecouplingStore } from './useTtftDecouplingStore';

interface DagProgressPulseTimelineProps {
  timeline: DagTimelineState;
  className?: string;
}

function renderStepIcon(status: DagStepNode['status']) {
  if (status === 'completed' || status === 'bypassed') {
    return <CheckCircle2 className="h-3 w-3 text-emerald-500" />;
  }
  if (status === 'running') {
    return <Activity className="h-3 w-3 text-primary animate-pulse" />;
  }
  if (status === 'failed') {
    return <XCircle className="h-3 w-3 text-destructive" />;
  }
  return <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40" />;
}

export const DagProgressPulseTimeline: React.FC<
  DagProgressPulseTimelineProps
> = ({ timeline, className = '' }) => {
  const isExpanded = useTtftDecouplingStore(
    (state) => state.isTimelineExpanded[timeline.dagId] ?? true,
  );
  const toggleTimelineExpansion = useTtftDecouplingStore(
    (state) => state.toggleTimelineExpansion,
  );

  const analysis = analyzeCriticalPathProgress(timeline.steps);
  const batches = groupStepsByParallelBatch(timeline.steps);

  return (
    <div
      data-testid={`dag-timeline-${timeline.dagId}`}
      className={`my-2 w-full max-w-xl rounded-xl border border-border/50 bg-background/70 p-3 text-xs shadow-2xs backdrop-blur-md dark:bg-muted/30 ${className}`}
    >
      {/* 头部进度条与状态概览 */}
      <div className="flex items-center justify-between gap-2 border-b border-border/40 pb-2">
        <div className="flex items-center gap-2">
          <div className="flex h-5 w-5 items-center justify-center rounded bg-primary/10 text-primary">
            <GitBranch className="h-3 w-3" />
          </div>
          <span className="font-semibold text-foreground">
            DAG 关键路径执行流水线
          </span>
          <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
            {analysis.completedSteps}/{analysis.totalSteps} 步完成 ·{' '}
            {analysis.progressPercent}%
          </span>
        </div>

        <button
          type="button"
          onClick={() => {
            toggleTimelineExpansion(timeline.dagId);
          }}
          aria-expanded={isExpanded}
          aria-label={isExpanded ? '收起关键路径时间轴' : '展开关键路径时间轴'}
          className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <span>{isExpanded ? '收起流式流水线' : '展开查看步骤'}</span>
          {isExpanded ? (
            <ChevronUp className="h-3 w-3" />
          ) : (
            <ChevronDown className="h-3 w-3" />
          )}
        </button>
      </div>

      {/* 线性总体进度条 */}
      <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={`h-full transition-all duration-300 ${
            timeline.isAllCompleted
              ? 'bg-emerald-500'
              : analysis.isCriticalPathBlocked
              ? 'bg-destructive'
              : 'bg-primary'
          }`}
          style={{ width: `${analysis.progressPercent}%` }}
        />
      </div>

      {/* 展开的节点流水线 */}
      {isExpanded && (
        <div
          data-testid="dag-nodes-container"
          className="mt-3 space-y-2 border-t border-border/20 pt-2"
        >
          {batches.map((batch) => {
            if (batch.isParallel) {
              return (
                <div
                  key={batch.groupId}
                  className="rounded-lg border border-primary/20 bg-primary/5 p-2"
                >
                  <div className="mb-1.5 flex items-center gap-1 text-[10px] font-medium text-primary">
                    <Zap className="h-2.5 w-2.5" />
                    <span>并行执行批次 ({batch.nodes.length} 个任务并发)</span>
                  </div>

                  <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                    {batch.nodes.map((node) => (
                      <div
                        key={node.id}
                        className={`flex items-center justify-between rounded border bg-background/80 px-2 py-1 text-[11px] ${
                          node.status === 'running'
                            ? 'border-primary/40 text-foreground font-medium shadow-2xs'
                            : 'border-border/30 text-muted-foreground'
                        }`}
                      >
                        <div className="flex items-center gap-1.5 overflow-hidden">
                          {renderStepIcon(node.status)}
                          <span className="truncate">{node.name}</span>
                        </div>

                        {node.elapsedMs !== undefined && (
                          <span className="flex items-center gap-0.5 font-mono text-[10px] text-muted-foreground">
                            <Clock className="h-2.5 w-2.5" />
                            {formatElapsedMs(node.elapsedMs)}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              );
            }

            const singleNode = batch.nodes[0];
            if (!singleNode) {
              return null;
            }

            return (
              <div
                key={singleNode.id}
                className={`flex items-center justify-between rounded-lg border px-2.5 py-1.5 text-[11px] transition-colors ${
                  singleNode.status === 'running'
                    ? 'border-primary/50 bg-primary/5 font-medium text-foreground'
                    : singleNode.status === 'completed'
                    ? 'border-border/40 bg-muted/20 text-muted-foreground'
                    : singleNode.status === 'failed'
                    ? 'border-destructive/40 bg-destructive/5 text-destructive'
                    : 'border-border/30 bg-background/40 text-muted-foreground/80'
                }`}
              >
                <div className="flex items-center gap-2 overflow-hidden">
                  <div className="flex h-4 w-4 shrink-0 items-center justify-center">
                    {renderStepIcon(singleNode.status)}
                  </div>
                  <span className="truncate">{singleNode.name}</span>
                  {singleNode.isCriticalPath && (
                    <span className="rounded bg-muted px-1 text-[9px] font-mono text-muted-foreground">
                      关键路径
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {singleNode.elapsedMs !== undefined && (
                    <span className="flex items-center gap-0.5 font-mono text-[10px] text-muted-foreground">
                      <Clock className="h-2.5 w-2.5" />
                      {formatElapsedMs(singleNode.elapsedMs)}
                    </span>
                  )}
                  {singleNode.status === 'running' && (
                    <span className="animate-pulse text-[10px] text-primary">
                      执行中...
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
