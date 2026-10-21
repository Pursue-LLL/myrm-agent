import { describe, it, expect } from 'vitest';
import {
  deriveTriSurfaceState,
  validateConnectionEpoch,
  computeDiffStats,
  DEFAULT_MOCK_CHANGES,
  DEFAULT_BOOTSTRAP_PAYLOAD,
} from '../dockableWorkbenchEngine';
import type { TriSurfaceTaskState, FileChangeItem } from '../dockableWorkbenchTypes';

describe('dockableWorkbenchEngine', () => {
  it('预设数据结构应完备合法', () => {
    expect(DEFAULT_MOCK_CHANGES.length).toBeGreaterThanOrEqual(3);
    expect(DEFAULT_BOOTSTRAP_PAYLOAD.sessionId).toBe('session-main-001');
    expect(DEFAULT_BOOTSTRAP_PAYLOAD.sandboxChanges.length).toBeGreaterThan(0);
  });

  describe('deriveTriSurfaceState', () => {
    const mockTask: TriSurfaceTaskState = {
      taskId: 't-1',
      status: 'running',
      currentTool: 'write_file',
      stepIndex: 2,
      totalSteps: 4,
      epoch: 1,
      sequenceNo: 8,
      progressPercentage: 50,
      lastMessage: '执行中',
    };

    it('无论针对何种表面形态，派生出的状态与进度必须保持 100% 绝对一致', () => {
      const collapsed = deriveTriSurfaceState(mockTask, 'collapsed_row');
      const expanded = deriveTriSurfaceState(mockTask, 'expanded_card');
      const drawer = deriveTriSurfaceState(mockTask, 'detail_drawer');

      expect(collapsed.displayStatus).toBe('正在执行');
      expect(expanded.displayStatus).toBe('正在执行');
      expect(drawer.displayStatus).toBe('正在执行');

      expect(collapsed.progressText).toBe('2 / 4 步 (50%)');
      expect(expanded.progressText).toBe('2 / 4 步 (50%)');
      expect(drawer.progressText).toBe('2 / 4 步 (50%)');

      expect(collapsed.isSynced).toBe(true);
      expect(expanded.isSynced).toBe(true);
      expect(drawer.isSynced).toBe(true);
    });

    it('针对不同形态定制合适的语义摘要文本', () => {
      const collapsed = deriveTriSurfaceState(mockTask, 'collapsed_row');
      const expanded = deriveTriSurfaceState(mockTask, 'expanded_card');
      const drawer = deriveTriSurfaceState(mockTask, 'detail_drawer');

      expect(collapsed.currentActionSummary).toContain('调用工具: write_file');
      expect(expanded.currentActionSummary).toContain('正在执行步骤 [2]');
      expect(drawer.currentActionSummary).toContain('代次 E1#8');
    });

    it('当任务完成或失败时能正确映射状态颜色与文字', () => {
      const completedTask: TriSurfaceTaskState = { ...mockTask, status: 'completed' };
      const failedTask: TriSurfaceTaskState = { ...mockTask, status: 'failed' };

      expect(deriveTriSurfaceState(completedTask, 'collapsed_row').displayStatus).toBe('已完成');
      expect(deriveTriSurfaceState(completedTask, 'collapsed_row').statusColor).toBe('emerald');

      expect(deriveTriSurfaceState(failedTask, 'collapsed_row').displayStatus).toBe('执行失败');
      expect(deriveTriSurfaceState(failedTask, 'collapsed_row').statusColor).toBe('rose');
    });
  });

  describe('validateConnectionEpoch', () => {
    it('应拒绝旧代次（断线前代次）事件，防止污染时序基线', () => {
      const isValid = validateConnectionEpoch(1, 2, 10, 0);
      expect(isValid).toBe(false);
    });

    it('同一代次内序号非递增时应拒绝（防重放）', () => {
      const isReplay = validateConnectionEpoch(2, 2, 5, 5);
      expect(isReplay).toBe(false);

      const isOldSeq = validateConnectionEpoch(2, 2, 3, 5);
      expect(isOldSeq).toBe(false);
    });

    it('合法代次与递增序号应允许通过', () => {
      const isOkSameEpoch = validateConnectionEpoch(2, 2, 6, 5);
      expect(isOkSameEpoch).toBe(true);

      const isOkNewEpoch = validateConnectionEpoch(3, 2, 1, 100);
      expect(isOkNewEpoch).toBe(true);
    });
  });

  describe('computeDiffStats', () => {
    it('能正确计算变更文件总行数与文件数', () => {
      const items: FileChangeItem[] = [
        { path: 'a.ts', changeType: 'added', additions: 10, deletions: 0, diffHunk: '' },
        { path: 'b.ts', changeType: 'modified', additions: 5, deletions: 3, diffHunk: '' },
      ];

      const stats = computeDiffStats(items);
      expect(stats.changedFilesCount).toBe(2);
      expect(stats.totalAdditions).toBe(15);
      expect(stats.totalDeletions).toBe(3);
    });
  });
});
