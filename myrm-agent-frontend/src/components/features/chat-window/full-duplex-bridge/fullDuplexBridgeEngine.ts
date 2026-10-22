import {
  BackgroundWorkerStatus,
  BackgroundWorkerTask,
  ReanchoredResultCard,
} from './fullDuplexBridgeTypes';

/**
 * 计算后台 Worker 的预估剩余耗时 (ETA, 秒)
 */
export function calculateWorkerEta(
  progress: number,
  elapsedSec: number,
  fallbackEstimatedTotalSec = 120,
): number {
  if (progress <= 0) {
    return Math.max(0, fallbackEstimatedTotalSec - elapsedSec);
  }

  if (progress >= 100) {
    return 0;
  }

  // 若进度极低（小于 5%），避免早期线性推算巨大波动
  if (progress < 5) {
    const rawRemain = fallbackEstimatedTotalSec - elapsedSec;
    return Math.max(5, rawRemain);
  }

  const projectedTotalSec = (elapsedSec / progress) * 100;
  const eta = projectedTotalSec - elapsedSec;
  return Math.max(0, Math.round(eta));
}

/**
 * 格式化持续耗时或 ETA
 */
export function formatDuration(seconds: number): string {
  const safeSec = Math.max(0, Math.floor(seconds));
  if (safeSec < 60) {
    return `${safeSec}s`;
  }

  const mins = Math.floor(safeSec / 60);
  const remainingSec = safeSec % 60;
  if (mins < 60) {
    if (remainingSec === 0) {
      return `${mins}m`;
    }
    return `${mins}m ${remainingSec}s`;
  }

  const hours = Math.floor(mins / 60);
  const remainingMins = mins % 60;
  return `${hours}h ${remainingMins}m`;
}

export interface AggregatedWorkerProgress {
  totalCount: number;
  runningCount: number;
  completedCount: number;
  failedCount: number;
  averageProgress: number;
  hasActive: boolean;
  topActiveTitle?: string;
}

/**
 * 聚合当前所有后台 Worker 的并发状态与总览进度
 */
export function calculateAggregatedProgress(
  workers: BackgroundWorkerTask[],
): AggregatedWorkerProgress {
  if (workers.length === 0) {
    return {
      totalCount: 0,
      runningCount: 0,
      completedCount: 0,
      failedCount: 0,
      averageProgress: 0,
      hasActive: false,
    };
  }

  let runningCount = 0;
  let completedCount = 0;
  let failedCount = 0;
  let totalProgress = 0;
  let topActiveTitle: string | undefined;

  for (const worker of workers) {
    totalProgress += worker.progress;
    if (worker.status === 'running' || worker.status === 'queued') {
      runningCount += 1;
      if (!topActiveTitle) {
        topActiveTitle = worker.title;
      }
    } else if (worker.status === 'completed') {
      completedCount += 1;
    } else if (worker.status === 'failed' || worker.status === 'canceled') {
      failedCount += 1;
    }
  }

  const averageProgress = Math.round(totalProgress / workers.length);

  return {
    totalCount: workers.length,
    runningCount,
    completedCount,
    failedCount,
    averageProgress,
    hasActive: runningCount > 0,
    topActiveTitle,
  };
}

export interface ReanchorPlacementResult {
  placementIndex: number;
  strategy: 'bottom_append' | 'after_anchor';
  anchorFound: boolean;
}

/**
 * 决定成果就绪卡片在当前会话消息列表中的插播锚点
 */
export function resolveReanchorPlacement(
  messageIds: string[],
  targetMessageAnchorId?: string,
): ReanchorPlacementResult {
  if (!targetMessageAnchorId || messageIds.length === 0) {
    return {
      placementIndex: messageIds.length,
      strategy: 'bottom_append',
      anchorFound: false,
    };
  }

  const anchorIdx = messageIds.indexOf(targetMessageAnchorId);
  if (anchorIdx === -1) {
    return {
      placementIndex: messageIds.length,
      strategy: 'bottom_append',
      anchorFound: false,
    };
  }

  return {
    placementIndex: anchorIdx + 1,
    strategy: 'after_anchor',
    anchorFound: true,
  };
}

/**
 * 生成成果采纳引用文本，用于回填到输入框
 */
export function generateAdoptionSnippet(card: ReanchoredResultCard): string {
  const artifact = card.artifact;
  return `针对后台生成的成果《${card.title}》（${artifact.summary}），请基于此继续：`;
}
