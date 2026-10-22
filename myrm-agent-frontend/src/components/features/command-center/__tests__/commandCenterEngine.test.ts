import { describe, it, expect } from 'vitest';
import {
  isCommandCenterShortcut,
  filterSessions,
  generateSessionAuditPack,
  generateDebugShareBundle,
  getDefaultSessions,
  getDefaultHealth,
  getDefaultUsageSummary,
  getDefaultLogs,
} from '../commandCenterEngine';

describe('commandCenterEngine', () => {
  it('isCommandCenterShortcut 应正确识别 Cmd+. / Ctrl+. 以及 Cmd+K / Ctrl+K', () => {
    // 模拟 Period 键
    const periodEvt = {
      metaKey: true,
      ctrlKey: false,
      key: '.',
      code: 'Period',
    } as unknown as KeyboardEvent;
    expect(isCommandCenterShortcut(periodEvt)).toBe(true);

    // 模拟 K 键
    const kEvt = {
      metaKey: true,
      ctrlKey: false,
      key: 'k',
      code: 'KeyK',
    } as unknown as KeyboardEvent;
    expect(isCommandCenterShortcut(kEvt)).toBe(true);

    // 无修饰键
    const plainEvt = {
      metaKey: false,
      ctrlKey: false,
      key: 'k',
      code: 'KeyK',
    } as unknown as KeyboardEvent;
    expect(isCommandCenterShortcut(plainEvt)).toBe(false);
  });

  it('filterSessions 应优先将置顶项置于顶部并支持关键词与标签过滤', () => {
    const sessions = getDefaultSessions();

    const filteredUX = filterSessions(sessions, 'UX');
    expect(filteredUX.length).toBeGreaterThanOrEqual(1);
    expect(filteredUX[0].tags).toContain('UX');

    const filteredArch = filterSessions(sessions, 'Arch-Master-4o');
    expect(filteredArch.length).toBeGreaterThanOrEqual(1);
    expect(filteredArch[0].agentName).toBe('Arch-Master-4o');

    // 验证置顶项优先
    const allSorted = filterSessions(sessions, '');
    expect(allSorted[0].isPinned).toBe(true);
  });

  it('generateSessionAuditPack 应打包结构化的 Markdown 报告与 JSON 元数据', () => {
    const session = getDefaultSessions()[0];
    const pack = generateSessionAuditPack(session);

    expect(pack.sessionId).toBe(session.id);
    expect(pack.title).toBe(session.title);
    expect(pack.summaryMarkdown).toContain('# 📋 Myrm 权威会话审计报告');
    expect(pack.summaryMarkdown).toContain(session.agentName);
    expect(pack.rawJsonData).toContain(session.id);
  });

  it('generateDebugShareBundle 应脱敏常见秘钥与敏感路径', () => {
    const logs = [
      {
        id: '1',
        timestamp: '12:00:00',
        level: 'error' as const,
        component: 'agent' as const,
        message:
          'Failed request with token sk-abcdef1234567890abcdef123456 at /Users/john_doe/project',
      },
    ];
    const health = getDefaultHealth();
    const bundleStr = generateDebugShareBundle(logs, health);
    const bundle = JSON.parse(bundleStr);

    expect(bundle).toHaveProperty('gatewayHealth');
    expect(bundle.recentSanitizedLogs[0]).toContain('sk-***[REDACTED]***');
    expect(bundle.recentSanitizedLogs[0]).toContain('/Users/***USER***/');
  });

  it('getDefaultUsageSummary 应根据天数跨度提供正确的乘数指标', () => {
    const summary7 = getDefaultUsageSummary(7);
    const summary30 = getDefaultUsageSummary(30);

    expect(summary7.horizonDays).toBe(7);
    expect(summary30.horizonDays).toBe(30);
    expect(summary30.totalSessions).toBe(summary7.totalSessions * 4);
    expect(summary7.topModels.length).toBeGreaterThanOrEqual(3);
    expect(summary7.topSkills.length).toBeGreaterThanOrEqual(4);
  });
});
