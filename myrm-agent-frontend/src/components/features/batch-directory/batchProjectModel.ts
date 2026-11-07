/**
 * [INPUT] @/services/batch-directory::BatchProject / BatchProjectDetail / BatchTaskItem / isBatchTerminalStatus (POS: 批量目录数据类型与终态判定)
 * [OUTPUT] formatDateTime / batchProgressPercent / deriveProjectFlags / isTaskRetryable: 列表页与详情页共用的纯函数
 * [POS] BatchDirectory 展示层的纯逻辑：时间格式化、进度百分比、项目状态派生标志、任务可重试判定。
 */

import {
  isBatchTerminalStatus,
  type BatchProject,
  type BatchProjectDetail,
  type BatchTaskItem,
} from '@/services/batch-directory';

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) {
    return '—';
  }
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    return '—';
  }
  return d.toLocaleString();
}

export function batchProgressPercent(
  project: Pick<BatchProject, 'total_tasks' | 'completed_tasks' | 'failed_tasks'>,
): number {
  const total = project.total_tasks || 0;
  if (total === 0) {
    return 0;
  }
  return Math.round(((project.completed_tasks + project.failed_tasks) / total) * 100);
}

export interface BatchProjectFlags {
  running: boolean;
  paused: boolean;
  terminal: boolean;
  /** 运行中或已暂停，仍可取消。 */
  active: boolean;
  inReviewCount: number;
  /** 存在失败目录或缺失产物的目录，可整体重试。 */
  hasRetryable: boolean;
}

export function deriveProjectFlags(project: BatchProjectDetail): BatchProjectFlags {
  const running = project.status === 'running';
  const paused = project.status === 'paused';
  return {
    running,
    paused,
    terminal: isBatchTerminalStatus(project.status),
    active: running || paused,
    inReviewCount: project.tasks.filter((task) => task.status === 'in_review').length,
    hasRetryable:
      (project.failed_directories?.length ?? 0) > 0 || (project.missing_artifact_directories?.length ?? 0) > 0,
  };
}

export function isTaskRetryable(task: BatchTaskItem): boolean {
  return (
    task.status === 'failed' ||
    task.status === 'archived' ||
    (task.status === 'completed' && task.artifact_status === 'missing')
  );
}
