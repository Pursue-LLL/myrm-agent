import { DagStepNode } from './ttftDecouplingTypes';

/**
 * 计算推测性即时确认从发射到前端渲染的握手延迟 (ms)
 */
export function computeSpeculativeLatency(
  ackTimestamp: number,
  currentTimestamp: number = Date.now(),
): number {
  const diff = currentTimestamp - ackTimestamp;
  return Math.max(10, Math.round(diff));
}

/**
 * 格式化毫秒或秒级耗时
 */
export function formatElapsedMs(ms: number): string {
  const safeMs = Math.max(0, Math.round(ms));
  if (safeMs < 1000) {
    return `${safeMs}ms`;
  }
  return `${(safeMs / 1000).toFixed(1)}s`;
}

export interface CriticalPathAnalysisResult {
  totalSteps: number;
  completedSteps: number;
  criticalPathTotal: number;
  criticalPathCompleted: number;
  isCriticalPathBlocked: boolean;
  progressPercent: number;
}

/**
 * 分析 DAG 关键路径推进状态与整体完成率
 */
export function analyzeCriticalPathProgress(
  steps: DagStepNode[],
): CriticalPathAnalysisResult {
  if (steps.length === 0) {
    return {
      totalSteps: 0,
      completedSteps: 0,
      criticalPathTotal: 0,
      criticalPathCompleted: 0,
      isCriticalPathBlocked: false,
      progressPercent: 0,
    };
  }

  let completedSteps = 0;
  let criticalPathTotal = 0;
  let criticalPathCompleted = 0;
  let isCriticalPathBlocked = false;

  for (const step of steps) {
    if (step.status === 'completed' || step.status === 'bypassed') {
      completedSteps += 1;
    }

    if (step.isCriticalPath) {
      criticalPathTotal += 1;
      if (step.status === 'completed' || step.status === 'bypassed') {
        criticalPathCompleted += 1;
      } else if (step.status === 'failed') {
        isCriticalPathBlocked = true;
      }
    }
  }

  const progressPercent = Math.round((completedSteps / steps.length) * 100);

  return {
    totalSteps: steps.length,
    completedSteps,
    criticalPathTotal,
    criticalPathCompleted,
    isCriticalPathBlocked,
    progressPercent,
  };
}

export interface StepBatchGroup {
  groupId: string;
  isParallel: boolean;
  nodes: DagStepNode[];
}

/**
 * 将平铺的 DAG 节点按并行组 (parallelGroupId) 汇聚切分，用于时间轴并排渲染
 */
export function groupStepsByParallelBatch(
  steps: DagStepNode[],
): StepBatchGroup[] {
  const groups: StepBatchGroup[] = [];
  let currentParallelId: string | undefined;
  let currentBatch: DagStepNode[] = [];

  for (const step of steps) {
    if (step.parallelGroupId) {
      if (step.parallelGroupId === currentParallelId) {
        currentBatch.push(step);
      } else {
        if (currentBatch.length > 0) {
          groups.push({
            groupId: currentParallelId ?? `batch-${groups.length}`,
            isParallel: Boolean(currentParallelId),
            nodes: currentBatch,
          });
        }
        currentParallelId = step.parallelGroupId;
        currentBatch = [step];
      }
    } else {
      if (currentBatch.length > 0) {
        groups.push({
          groupId: currentParallelId ?? `batch-${groups.length}`,
          isParallel: Boolean(currentParallelId),
          nodes: currentBatch,
        });
        currentBatch = [];
        currentParallelId = undefined;
      }
      groups.push({
        groupId: `single-${step.id}`,
        isParallel: false,
        nodes: [step],
      });
    }
  }

  if (currentBatch.length > 0) {
    groups.push({
      groupId: currentParallelId ?? `batch-${groups.length}`,
      isParallel: Boolean(currentParallelId),
      nodes: currentBatch,
    });
  }

  return groups;
}
