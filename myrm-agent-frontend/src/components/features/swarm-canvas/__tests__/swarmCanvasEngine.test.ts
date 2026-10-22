import { describe, expect, it } from 'vitest';
import {
  calculateSwarmSummaryStats,
  deriveAdaptiveGridColumns,
  filterWorkersByStatus,
  formatSwarmStatusCapsuleLabel,
  formatWorkerStatusBadge,
} from '../swarmCanvasEngine';
import type { SwarmWorkerItem } from '../swarmCanvasTypes';

describe('swarmCanvasEngine', () => {
  const mockWorkers: SwarmWorkerItem[] = [
    {
      id: 'w1',
      name: '爬虫',
      role: '抓取',
      colorTheme: '#3b82f6',
      status: 'completed',
      currentTaskTitle: '抓取文章',
      progressPercent: 100,
      thinkingLogs: [],
      toolCalls: [],
      createdAt: 1000,
    },
    {
      id: 'w2',
      name: '推演',
      role: '计算',
      colorTheme: '#10b981',
      status: 'running',
      currentTaskTitle: '计算指标',
      progressPercent: 60,
      thinkingLogs: [],
      toolCalls: [],
      createdAt: 2000,
    },
    {
      id: 'w3',
      name: '审批',
      role: '安全',
      colorTheme: '#f59e0b',
      status: 'waiting_approval',
      currentTaskTitle: '等待授权',
      progressPercent: 30,
      thinkingLogs: [],
      toolCalls: [],
      createdAt: 3000,
    },
    {
      id: 'w4',
      name: '测试',
      role: '验证',
      colorTheme: '#ef4444',
      status: 'failed',
      currentTaskTitle: '脚本错误',
      progressPercent: 10,
      thinkingLogs: [],
      toolCalls: [],
      createdAt: 4000,
    },
  ];

  it('正确计算集群统计指标与平均进度', () => {
    const stats = calculateSwarmSummaryStats(mockWorkers);
    expect(stats.total).toBe(4);
    expect(stats.completed).toBe(1);
    expect(stats.running).toBe(1);
    expect(stats.waitingApproval).toBe(1);
    expect(stats.failed).toBe(1);
    expect(stats.progressPercent).toBe(50); // (100 + 60 + 30 + 10) / 4 = 50%
  });

  it('自适应动态计算网格列数，避免 DOM 遮挡', () => {
    expect(deriveAdaptiveGridColumns(1)).toBe('grid-cols-1');
    expect(deriveAdaptiveGridColumns(2)).toBe('grid-cols-1 sm:grid-cols-2');
    expect(deriveAdaptiveGridColumns(4)).toBe(
      'grid-cols-1 sm:grid-cols-2 lg:grid-cols-2'
    );
    expect(deriveAdaptiveGridColumns(6)).toBe(
      'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'
    );
    expect(deriveAdaptiveGridColumns(12)).toBe(
      'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5'
    );
  });

  it('按状态过滤智能体列表', () => {
    const all = filterWorkersByStatus(mockWorkers, 'all');
    expect(all.length).toBe(4);

    const runningOnly = filterWorkersByStatus(mockWorkers, 'running');
    expect(runningOnly.length).toBe(1);
    expect(runningOnly[0].id).toBe('w2');

    const completedOnly = filterWorkersByStatus(mockWorkers, 'completed');
    expect(completedOnly.length).toBe(1);
    expect(completedOnly[0].id).toBe('w1');
  });

  it('格式化集群状态胶囊徽标文本', () => {
    const stats = calculateSwarmSummaryStats(mockWorkers);
    const label = formatSwarmStatusCapsuleLabel(stats);
    expect(label).toContain('1 已达成');
    expect(label).toContain('1 运行中');
    expect(label).toContain('1 待授权');
    expect(label).toContain('1 异常');
  });

  it('派生智能体单卡片状态样式与光晕色', () => {
    const runningBadge = formatWorkerStatusBadge('running');
    expect(runningBadge.label).toBe('执行中');
    expect(runningBadge.badgeText).toContain('text-emerald-400');

    const approvalBadge = formatWorkerStatusBadge('waiting_approval');
    expect(approvalBadge.label).toBe('待授权');
    expect(approvalBadge.badgeText).toContain('text-amber-400');
  });
});
