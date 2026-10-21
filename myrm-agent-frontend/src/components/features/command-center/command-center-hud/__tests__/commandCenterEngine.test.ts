import { describe, it, expect } from 'vitest';
import {
  filterWorkstreams,
  formatSpendTokens,
  formatSpendUsd,
  runSystemDoctorDiagnostic,
  remediateDiagnosticIssue,
  generateConfigBackupPayload,
} from '../commandCenterEngine';
import { DiagnosticCheckItem, PinnedWorkstream } from '../commandCenterTypes';

describe('commandCenterEngine', () => {
  const mockWorkstreams: PinnedWorkstream[] = [
    {
      id: 'ws-1',
      title: 'UI 原型设计与营销海报',
      lastActive: '5分钟前',
      category: 'workflow',
      isPinned: false,
    },
    {
      id: 'ws-2',
      title: '网关调度与长任务并发',
      lastActive: '10分钟前',
      category: 'chat',
      isPinned: true,
    },
    {
      id: 'ws-3',
      title: 'Hermes 跨进程协议对接',
      lastActive: '1小时前',
      category: 'artifact',
      isPinned: false,
    },
  ];

  const mockChecks: DiagnosticCheckItem[] = [
    {
      id: 'chk-gateway',
      category: 'gateway',
      name: '网关服务',
      status: 'warning',
      detail: '高延迟告警',
      remediable: false,
    },
    {
      id: 'chk-sandbox',
      category: 'sandbox',
      name: '安全沙箱',
      status: 'error',
      detail: '沙箱磁盘已满',
      remediable: true,
    },
  ];

  it('filters workstreams by query and prioritizes pinned items', () => {
    // 空 query：置顶的 ws-2 排在最前
    const defaultSorted = filterWorkstreams(mockWorkstreams, '');
    expect(defaultSorted[0].id).toBe('ws-2');

    // 模糊检索 "原型"
    const matched = filterWorkstreams(mockWorkstreams, '原型');
    expect(matched.length).toBe(1);
    expect(matched[0].id).toBe('ws-1');

    // 模糊检索分类 "chat"
    const byCategory = filterWorkstreams(mockWorkstreams, 'chat');
    expect(byCategory.length).toBe(1);
    expect(byCategory[0].id).toBe('ws-2');

    // 无匹配
    const noMatch = filterWorkstreams(mockWorkstreams, 'nonexistent');
    expect(noMatch.length).toBe(0);
  });

  it('formats token spend numbers accurately', () => {
    expect(formatSpendTokens(800)).toBe('800');
    expect(formatSpendTokens(45200)).toBe('45.2k');
    expect(formatSpendTokens(1420000)).toBe('1.42M');
  });

  it('formats USD spend currency values accurately', () => {
    expect(formatSpendUsd(0)).toBe('$0.00');
    expect(formatSpendUsd(0.005)).toBe('< $0.01');
    expect(formatSpendUsd(2.48)).toBe('$2.48');
    expect(formatSpendUsd(12.345)).toBe('$12.35');
  });

  it('runs system doctor diagnostics and verifies checks', () => {
    const results = runSystemDoctorDiagnostic(mockChecks);
    const gateway = results.find((c) => c.category === 'gateway');
    expect(gateway?.status).toBe('pass');
    expect(gateway?.detail).toContain('握手正常');
  });

  it('remediates diagnostic issues in-place', () => {
    const remediated = remediateDiagnosticIssue(mockChecks, 'chk-sandbox');
    const sandbox = remediated.find((c) => c.id === 'chk-sandbox');

    expect(sandbox?.status).toBe('pass');
    expect(sandbox?.remediable).toBe(false);
    expect(sandbox?.detail).toContain('已就地自愈修复');
  });

  it('generates valid JSON config backup payload', () => {
    const payload = generateConfigBackupPayload(mockWorkstreams, mockChecks);
    const parsed = JSON.parse(payload);

    expect(parsed.systemVersion).toBe('0.21.0-commercial');
    expect(parsed.totalWorkstreamsCount).toBe(3);
    expect(parsed.workstreams.length).toBe(3);
    expect(parsed.healthAudit.totalChecks).toBe(2);
  });
});
