import { describe, it, expect } from 'vitest';
import type {
  LaneType,
  LaneEnvironmentMode,
  LaneCapability,
  PersistenceScope,
  GraduationTriggerKind,
  LaneGradientSpec,
  GraduationIntentMatch,
  LaneGraduationEvent,
} from '../laneSemanticTypes';

describe('laneSemanticTypes', () => {
  it('correctly models LaneGradientSpec contract', () => {
    const spec: LaneGradientSpec = {
      laneType: 'workspace',
      envMode: 'local_workspace',
      displayName: '本地工作区',
      summary: '直连本地磁盘',
      capabilities: ['file_write', 'shell_exec'],
      persistenceScope: 'local_disk',
      canWriteFiles: true,
      canExecCommands: true,
      badgeColor: 'emerald',
    };

    expect(spec.laneType).toBe('workspace');
    expect(spec.envMode).toBe('local_workspace');
    expect(spec.capabilities).toContain<LaneCapability>('file_write');
    expect(spec.persistenceScope).toBe<PersistenceScope>('local_disk');
    expect(spec.canWriteFiles).toBe(true);
  });

  it('correctly models GraduationIntentMatch contract', () => {
    const match: GraduationIntentMatch = {
      triggerKind: 'file_write',
      matchedKeyword: '保存到',
      confidence: 0.92,
      reason: '需要写入磁盘',
      suggestedTargetMode: 'local_workspace',
      detectedSnippet: '请将代码保存到 src/index.ts',
    };

    expect(match.triggerKind).toBe<GraduationTriggerKind>('file_write');
    expect(match.confidence).toBeGreaterThan(0.9);
    expect(match.suggestedTargetMode).toBe<LaneEnvironmentMode>('local_workspace');
  });

  it('correctly models LaneGraduationEvent contract', () => {
    const event: LaneGraduationEvent = {
      id: 'grad_123',
      timestamp: 1760000000000,
      fromLane: 'chat' as LaneType,
      fromEnvMode: 'fast_chat' as LaneEnvironmentMode,
      toLane: 'workspace' as LaneType,
      toEnvMode: 'local_workspace' as LaneEnvironmentMode,
      reason: '检测到写入意图',
      workspaceDir: '/projects/app',
    };

    expect(event.fromLane).toBe('chat');
    expect(event.toLane).toBe('workspace');
    expect(event.workspaceDir).toBe('/projects/app');
  });
});
