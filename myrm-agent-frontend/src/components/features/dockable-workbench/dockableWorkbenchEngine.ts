import type {
  BootstrapSessionPayload,
  DerivedSurfaceView,
  FileChangeItem,
  TriSurfaceMode,
  TriSurfaceTaskState,
} from './dockableWorkbenchTypes';

export function deriveTriSurfaceState(
  task: TriSurfaceTaskState,
  surface: TriSurfaceMode
): DerivedSurfaceView {
  let displayStatus = '准备中';
  let statusColor = 'slate';

  if (task.status === 'running') {
    displayStatus = '正在执行';
    statusColor = 'indigo';
  } else if (task.status === 'completed') {
    displayStatus = '已完成';
    statusColor = 'emerald';
  } else if (task.status === 'failed') {
    displayStatus = '执行失败';
    statusColor = 'rose';
  }

  const progressText = `${task.stepIndex} / ${task.totalSteps} 步 (${task.progressPercentage}%)`;

  let currentActionSummary = task.lastMessage ?? '任务准备就绪';
  if (task.status === 'running' && task.currentTool) {
    if (surface === 'collapsed_row') {
      currentActionSummary = `调用工具: ${task.currentTool}`;
    } else if (surface === 'expanded_card') {
      currentActionSummary = `正在执行步骤 [${task.stepIndex}] · 调度工具: ${task.currentTool}`;
    } else {
      currentActionSummary = `代次 E${task.epoch}#${task.sequenceNo} · 正在执行 [${task.currentTool}]`;
    }
  }

  return {
    displayStatus,
    statusColor,
    progressText,
    currentActionSummary,
    isSynced: true,
  };
}

export function validateConnectionEpoch(
  incomingEpoch: number,
  currentEpoch: number,
  incomingSeq: number,
  lastSeq: number
): boolean {
  // 旧重连代次的过期事件坚决丢弃，防止断线期间时序混乱污染
  if (incomingEpoch < currentEpoch) {
    return false;
  }

  // 同一代次内序号必须严格递增，防重放攻击
  if (incomingEpoch === currentEpoch && incomingSeq <= lastSeq) {
    return false;
  }

  return true;
}

export function computeDiffStats(changes: readonly FileChangeItem[]): {
  totalAdditions: number;
  totalDeletions: number;
  changedFilesCount: number;
} {
  let totalAdditions = 0;
  let totalDeletions = 0;

  for (const item of changes) {
    totalAdditions += item.additions;
    totalDeletions += item.deletions;
  }

  return {
    totalAdditions,
    totalDeletions,
    changedFilesCount: changes.length,
  };
}

export const DEFAULT_MOCK_CHANGES: readonly FileChangeItem[] = [
  {
    path: 'src/config/runtimePolicy.ts',
    changeType: 'modified',
    additions: 12,
    deletions: 3,
    diffHunk: `@@ -40,3 +40,12 @@
+export const SECURE_WORKSPACE_ROOT = '/sandbox/workspace';
+export const ENABLE_AUTO_RECOVERY = true;`,
  },
  {
    path: 'src/services/apiGateway.ts',
    changeType: 'modified',
    additions: 25,
    deletions: 8,
    diffHunk: `@@ -110,8 +110,25 @@
-const RETRY_ATTEMPTS = 1;
+const RETRY_ATTEMPTS = 3;
+export function dispatchEventWithEpoch(epoch: number) { ... }`,
  },
  {
    path: 'tests/runtimePolicy.test.ts',
    changeType: 'added',
    additions: 45,
    deletions: 0,
    diffHunk: `@@ -0,0 +1,45 @@
+import { describe, it, expect } from 'vitest';
+describe('runtimePolicy', () => { ... });`,
  },
];

export const DEFAULT_BOOTSTRAP_PAYLOAD: BootstrapSessionPayload = {
  sessionId: 'session-main-001',
  sessionTitle: '全栈智能体架构重构长会话',
  activeAgentName: '系统主架构师',
  sandboxChanges: DEFAULT_MOCK_CHANGES,
  eventBaselineEpoch: 1,
  initialMessagesCount: 24,
  cachedAt: '2026-10-15T18:00:00.000Z',
};
