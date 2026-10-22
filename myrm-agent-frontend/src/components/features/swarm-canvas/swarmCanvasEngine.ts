/**
 * swarmCanvasEngine.ts
 * 多智能体弹性网格自适应排版、状态统计与聚焦透镜纯函数引擎
 */

import type {
  SwarmSummaryStats,
  SwarmWorkerItem,
  SwarmWorkerStatus,
} from './swarmCanvasTypes';

export function calculateSwarmSummaryStats(
  workers: SwarmWorkerItem[]
): SwarmSummaryStats {
  const total = workers.length;
  if (total === 0) {
    return {
      total: 0,
      completed: 0,
      running: 0,
      waitingApproval: 0,
      failed: 0,
      progressPercent: 100,
    };
  }

  let completed = 0;
  let running = 0;
  let waitingApproval = 0;
  let failed = 0;
  let totalProgress = 0;

  for (const worker of workers) {
    totalProgress += worker.progressPercent;
    switch (worker.status) {
      case 'completed': {
        completed += 1;
        break;
      }
      case 'running': {
        running += 1;
        break;
      }
      case 'waiting_approval': {
        waitingApproval += 1;
        break;
      }
      case 'failed': {
        failed += 1;
        break;
      }
      case 'idle':
      default: {
        break;
      }
    }
  }

  const avgProgress = Math.min(100, Math.round(totalProgress / total));

  return {
    total,
    completed,
    running,
    waitingApproval,
    failed,
    progressPercent: avgProgress,
  };
}

export function deriveAdaptiveGridColumns(workerCount: number): string {
  if (workerCount <= 1) {
    return 'grid-cols-1';
  }
  if (workerCount === 2) {
    return 'grid-cols-1 sm:grid-cols-2';
  }
  if (workerCount <= 4) {
    return 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-2';
  }
  if (workerCount <= 8) {
    return 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4';
  }
  return 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5';
}

export function filterWorkersByStatus(
  workers: SwarmWorkerItem[],
  filter: SwarmWorkerStatus | 'all'
): SwarmWorkerItem[] {
  if (filter === 'all') {
    return workers;
  }
  return workers.filter((w) => w.status === filter);
}

export function formatSwarmStatusCapsuleLabel(
  stats: SwarmSummaryStats
): string {
  if (stats.total === 0) {
    return '空闲集群';
  }

  const parts: string[] = [];
  if (stats.completed > 0) {
    parts.push(`${stats.completed} 已达成`);
  }
  if (stats.running > 0) {
    parts.push(`${stats.running} 运行中`);
  }
  if (stats.waitingApproval > 0) {
    parts.push(`${stats.waitingApproval} 待授权`);
  }
  if (stats.failed > 0) {
    parts.push(`${stats.failed} 异常`);
  }

  if (parts.length === 0) {
    return `${stats.total} 就绪`;
  }

  return parts.join(' · ');
}

export function formatWorkerStatusBadge(status: SwarmWorkerStatus): {
  label: string;
  badgeBg: string;
  badgeText: string;
  haloColor: string;
} {
  switch (status) {
    case 'running': {
      return {
        label: '执行中',
        badgeBg: 'bg-emerald-950/80 border-emerald-700/60',
        badgeText: 'text-emerald-400',
        haloColor: 'rgba(16, 185, 129, 0.4)',
      };
    }
    case 'waiting_approval': {
      return {
        label: '待授权',
        badgeBg: 'bg-amber-950/80 border-amber-700/60',
        badgeText: 'text-amber-400',
        haloColor: 'rgba(245, 158, 11, 0.5)',
      };
    }
    case 'completed': {
      return {
        label: '已完成',
        badgeBg: 'bg-blue-950/80 border-blue-700/60',
        badgeText: 'text-blue-400',
        haloColor: 'rgba(59, 130, 246, 0.3)',
      };
    }
    case 'failed': {
      return {
        label: '已中断',
        badgeBg: 'bg-red-950/80 border-red-700/60',
        badgeText: 'text-red-400',
        haloColor: 'rgba(239, 68, 68, 0.5)',
      };
    }
    case 'idle':
    default: {
      return {
        label: '就绪',
        badgeBg: 'bg-slate-800/80 border-slate-700',
        badgeText: 'text-slate-400',
        haloColor: 'rgba(148, 163, 184, 0.2)',
      };
    }
  }
}
