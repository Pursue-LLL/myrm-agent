import { describe, it, expect } from 'vitest';
import {
  calculateRelayProgress,
  computeContentDiffLines,
  createArtifactForkBranch,
  advanceRelayPipeline,
} from '../relayPipelineEngine';
import { RelayStage, StageArtifactSnapshot } from '../multiRoleRelayTypes';

describe('relayPipelineEngine pure functions', () => {
  const mockSnapshot: StageArtifactSnapshot = {
    id: 'snap-1',
    stageId: 'stage-1',
    role: 'researcher',
    roleName: '调研员',
    artifactName: '竞品表.json',
    contentType: 'json',
    rawContent: '{\n  "price": "$29"\n}',
    summary: '调研完成',
    timestamp: 1000,
    tokenCount: 500,
    version: 1,
  };

  const mockStages: RelayStage[] = [
    {
      id: 'stage-1',
      stepNumber: 1,
      role: 'researcher',
      roleName: '调研员',
      status: 'completed',
      actionSummary: '调研完毕',
      durationMs: 3000,
      snapshot: mockSnapshot,
    },
    {
      id: 'stage-2',
      stepNumber: 2,
      role: 'analyst',
      roleName: '分析师',
      status: 'in_progress',
      actionSummary: '分析中',
      durationMs: 1500,
    },
    {
      id: 'stage-3',
      stepNumber: 3,
      role: 'copywriter',
      roleName: '撰稿人',
      status: 'pending',
      actionSummary: '等待中',
      durationMs: 0,
    },
  ];

  describe('calculateRelayProgress', () => {
    it('calculates progress percentage and active role', () => {
      const result = calculateRelayProgress(mockStages);
      expect(result.total).toBe(3);
      expect(result.completed).toBe(1);
      expect(result.progressPercent).toBe(33);
      expect(result.activeRole).toBe('分析师');
      expect(result.isFinished).toBe(false);
    });

    it('handles empty stage lists cleanly', () => {
      const result = calculateRelayProgress([]);
      expect(result.total).toBe(0);
      expect(result.completed).toBe(0);
      expect(result.progressPercent).toBe(0);
      expect(result.isFinished).toBe(false);
    });

    it('reports isFinished true when all stages are completed', () => {
      const completedStages: RelayStage[] = mockStages.map((s) => ({
        ...s,
        status: 'completed',
      }));
      const result = calculateRelayProgress(completedStages);
      expect(result.completed).toBe(3);
      expect(result.progressPercent).toBe(100);
      expect(result.isFinished).toBe(true);
    });
  });

  describe('computeContentDiffLines', () => {
    it('identifies unchanged, added, and removed lines between versions', () => {
      const original = '第一行原样\n第二行删除\n第三行原样';
      const modified = '第一行原样\n第二行新增修改\n第三行原样';

      const diff = computeContentDiffLines(original, modified);

      expect(diff.length).toBe(4);
      expect(diff[0].type).toBe('unchanged');
      expect(diff[0].text).toBe('第一行原样');

      expect(diff[1].type).toBe('removed');
      expect(diff[1].text).toBe('第二行删除');

      expect(diff[2].type).toBe('added');
      expect(diff[2].text).toBe('第二行新增修改');

      expect(diff[3].type).toBe('unchanged');
      expect(diff[3].text).toBe('第三行原样');
    });
  });

  describe('createArtifactForkBranch', () => {
    it('constructs fork branch with metadata and draft status', () => {
      const branch = createArtifactForkBranch(
        mockSnapshot,
        'conservative-pricing',
        '{\n  "price": "$39"\n}',
        '增加汇率波动防御准备金'
      );

      expect(branch.id.startsWith('fork-')).toBe(true);
      expect(branch.baseSnapshotId).toBe(mockSnapshot.id);
      expect(branch.stageId).toBe(mockSnapshot.stageId);
      expect(branch.branchName).toBe('conservative-pricing');
      expect(branch.modifiedContent).toContain('$39');
      expect(branch.userNote).toBe('增加汇率波动防御准备金');
      expect(branch.status).toBe('draft');
    });
  });

  describe('advanceRelayPipeline', () => {
    it('advances current stage to completed and sets next pending stage to in_progress', () => {
      const updatedStages = advanceRelayPipeline(mockStages, 'stage-2');

      const s2 = updatedStages.find((s) => s.id === 'stage-2');
      const s3 = updatedStages.find((s) => s.id === 'stage-3');

      expect(s2?.status).toBe('completed');
      expect(s2?.completedAt).toBeDefined();

      expect(s3?.status).toBe('in_progress');
      expect(s3?.startedAt).toBeDefined();
    });

    it('returns unmodified stages if current stage id is not found', () => {
      const unchanged = advanceRelayPipeline(mockStages, 'non-existent-stage');
      expect(unchanged).toEqual(mockStages);
    });
  });
});
