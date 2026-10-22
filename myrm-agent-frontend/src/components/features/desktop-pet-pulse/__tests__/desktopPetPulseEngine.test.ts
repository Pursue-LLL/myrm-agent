import { describe, expect, it } from 'vitest';
import {
  computeStackedAgentBadges,
  derivePetVisualConfig,
  executeDataMigrationMerge,
  formatVoiceDispatchPayload,
  validateMigrationBundle,
} from '../desktopPetPulseEngine';
import type {
  AgentIdentityProjection,
  DataMigrationBundle,
} from '../desktopPetPulseTypes';

describe('desktopPetPulseEngine', () => {
  it('正确派生桌宠视觉与微表情状态', () => {
    const idle = derivePetVisualConfig('idle');
    expect(idle.expression).toBe('calm');
    expect(idle.badgeLabel).toBe('就绪');

    const thinking = derivePetVisualConfig('thinking');
    expect(thinking.expression).toBe('pulsing');
    expect(thinking.badgeLabel).toBe('思考中');

    const working = derivePetVisualConfig('working');
    expect(working.expression).toBe('focused');
    expect(working.badgeLabel).toBe('执行中');

    const approval = derivePetVisualConfig('idle', true);
    expect(approval.expression).toBe('alert_shake');
    expect(approval.badgeLabel).toBe('待授权');

    const error = derivePetVisualConfig('idle', false, true);
    expect(error.expression).toBe('concerned');
    expect(error.badgeLabel).toBe('异常拦截');
  });

  it('计算次要智能体轻量堆叠徽标，排除主智能体', () => {
    const agents: AgentIdentityProjection[] = [
      { agentId: 'ag-1', name: '调度助手', colorTheme: '#3b82f6', isPrimary: true },
      { agentId: 'ag-2', name: '数据爬虫', colorTheme: '#10b981', isPrimary: false },
      { agentId: 'ag-3', name: '审计专员', colorTheme: '#f59e0b', isPrimary: false },
    ];

    const activeQueue = [
      { agentId: 'ag-1', status: 'working' as const },
      { agentId: 'ag-2', status: 'queued' as const },
      { agentId: 'ag-3', status: 'approving' as const },
    ];

    const badges = computeStackedAgentBadges('ag-1', agents, activeQueue);
    expect(badges.length).toBe(2);
    expect(badges[0].name).toBe('数据爬虫');
    expect(badges[0].status).toBe('queued');
    expect(badges[1].name).toBe('审计专员');
    expect(badges[1].status).toBe('approving');
  });

  it('格式化语音任务派发负载', () => {
    const payload = formatVoiceDispatchPayload(' 帮我总结当前项目进度  ', {
      targetAgentId: 'ag-1',
      autoRun: true,
    });
    expect(payload.prompt).toBe('帮我总结当前项目进度');
    expect(payload.targetAgentId).toBe('ag-1');
    expect(payload.autoRun).toBe(true);
    expect(payload.timestamp).toBeGreaterThan(0);
  });

  it('校验并解析数据迁移包', () => {
    const invalidRes = validateMigrationBundle(null);
    expect(invalidRes.valid).toBe(false);

    const missingVersion = validateMigrationBundle({ source: 'cursor' });
    expect(missingVersion.valid).toBe(false);

    const validRaw = {
      version: '1.2.0',
      source: 'cursor',
      tasks: [{ id: 't-1', title: 'test', prompt: 'p', createdAt: 12345 }],
      crons: [{ id: 'c-1', name: 'cron', schedule: '* * * * *', prompt: 'cp', enabled: true }],
    };
    const validRes = validateMigrationBundle(validRaw);
    expect(validRes.valid).toBe(true);
    expect(validRes.bundle?.source).toBe('cursor');
    expect(validRes.bundle?.tasks?.length).toBe(1);
    expect(validRes.bundle?.crons?.length).toBe(1);
  });

  it('执行数据平滑合并并应用跳过/覆盖策略', () => {
    const bundle: DataMigrationBundle = {
      version: '1.0.0',
      source: 'legacy_myrm',
      createdAt: 1000,
      tasks: [
        { id: 't-1', title: 'Task 1', prompt: 'p1', createdAt: 1000 },
        { id: 't-2', title: 'Task 2', prompt: 'p2', createdAt: 2000 },
      ],
      memories: [
        { id: 'm-1', key: 'lang', value: 'ts' },
      ],
    };

    const existingKeys = {
      tasks: new Set(['t-1']),
    };

    // 测试 skip 策略
    const skipReport = executeDataMigrationMerge(
      bundle,
      {
        selectedCategories: ['tasks', 'memories'],
        strategy: 'skip',
      },
      existingKeys
    );

    expect(skipReport.success).toBe(true);
    expect(skipReport.importedCounts.tasks).toBe(1);
    expect(skipReport.skippedCounts.tasks).toBe(1);
    expect(skipReport.importedCounts.memories).toBe(1);

    // 测试 overwrite 策略
    const overwriteReport = executeDataMigrationMerge(
      bundle,
      {
        selectedCategories: ['tasks'],
        strategy: 'overwrite',
      },
      existingKeys
    );

    expect(overwriteReport.importedCounts.tasks).toBe(2);
    expect(overwriteReport.skippedCounts.tasks).toBe(0);
  });
});
