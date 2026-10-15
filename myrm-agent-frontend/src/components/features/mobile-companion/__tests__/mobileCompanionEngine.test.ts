import { describe, it, expect } from 'vitest';
import {
  generatePairingConfig,
  formatTimeRemaining,
  filterHighSnrLogs,
  getPhaseBadgeInfo,
} from '../mobileCompanionEngine';

describe('mobileCompanionEngine', () => {
  it('正确生成会话配对配置、30分钟过期时间戳与 PWA 访问直链', () => {
    const config = generatePairingConfig('sess-test-123', 'https://agent.example.com');

    expect(config.sessionId).toBe('sess-test-123');
    expect(config.pairingToken).toContain('pair-');
    expect(config.pairingUrl).toContain('https://agent.example.com/m/task?session=sess-test-123&token=');
    expect(config.expiresAt).toBeGreaterThan(Date.now() + 25 * 60 * 1000);
    expect(config.isPwaInstallable).toBe(true);
  });

  it('人性化格式化剩余预计时间', () => {
    expect(formatTimeRemaining(0)).toBe('即将完成');
    expect(formatTimeRemaining(-5)).toBe('即将完成');
    expect(formatTimeRemaining(45)).toBe('约 45 秒');
    expect(formatTimeRemaining(120)).toBe('约 2 分钟');
    expect(formatTimeRemaining(150)).toBe('约 2 分 30 秒');
  });

  it('过滤底层琐碎安装与编译日志，保留高信噪比关键事件', () => {
    const raw = [
      'npm http 200 GET https://registry.npmjs.org/lodash',
      'fetch http://example.com/chunk-1.js',
      'at /workspace/compiler.js:12:4',
      '已搭建单页响应式布局，完成尺寸与材质动态系数公式',
      'transpiling file /src/Quoter.tsx',
      'downloading package esbuild@0.20.0',
      '正在沙箱中运行 12 组边缘测试用例',
    ];

    const filtered = filterHighSnrLogs(raw);
    expect(filtered.length).toBe(2);
    expect(filtered[0]).toBe('已搭建单页响应式布局，完成尺寸与材质动态系数公式');
    expect(filtered[1]).toBe('正在沙箱中运行 12 组边缘测试用例');
  });

  it('获取不同任务阶段的 PhaseBadge 样式与语义说明', () => {
    const initBadge = getPhaseBadgeInfo('initializing');
    expect(initBadge.label).toBe('环境初始化中');

    const testBadge = getPhaseBadgeInfo('testing');
    expect(testBadge.label).toBe('单元与回归测试');
    expect(testBadge.badgeClass).toContain('cyan');

    const apprBadge = getPhaseBadgeInfo('paused_approval');
    expect(apprBadge.label).toBe('等待人工高危审批');
    expect(apprBadge.badgeClass).toContain('amber');

    const doneBadge = getPhaseBadgeInfo('completed');
    expect(doneBadge.label).toBe('任务全部交付');
    expect(doneBadge.badgeClass).toContain('emerald');
  });
});
