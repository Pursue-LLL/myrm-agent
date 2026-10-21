import { describe, it, expect } from 'vitest';
import { extractCleanedActionItem } from '../smartFluffStripper';

describe('smartFluffStripper', () => {
  it('handles empty or whitespace strings gracefully', () => {
    const result = extractCleanedActionItem('   ');
    expect(result.rawText).toBe('');
    expect(result.actionableTitle).toBe('');
    expect(result.suggestedDescription).toBe('');
    expect(result.category).toBe('task');
    expect(result.urgency).toBe('low');
    expect(result.extractedBulletPoints).toEqual([]);
  });

  it('strips Chinese leading pleasantries and trailing confirmation requests', () => {
    const raw = '好的，根据您的要求，我建议重构消息流转模块为独立子包。您看这样合适吗？';
    const result = extractCleanedActionItem(raw);
    expect(result.actionableTitle).toBe('重构消息流转模块为独立子包');
    expect(result.category).toBe('refactor');
    expect(result.urgency).toBe('low');
  });

  it('strips English fluff and infers urgency and fix category', () => {
    const raw =
      'Certainly, based on the discussion, I suggest that we fix the urgent null pointer panic in the session hydrator. Do you think this works?';
    const result = extractCleanedActionItem(raw);
    expect(result.actionableTitle).toContain('fix the urgent null pointer panic in the session hydrator');
    expect(result.category).toBe('fix');
    expect(result.urgency).toBe('high');
  });

  it('extracts structured bullet points from multi-line assistant suggestions', () => {
    const raw = `
好的，结合当前上下文，以下是具体的执行方案：
1. 重构 DOM 节点反查算法
2. 修复流式看门狗超时异常
3. 验证端到端测试门禁
请问是否需要继续推进？
    `.trim();

    const result = extractCleanedActionItem(raw);
    expect(result.extractedBulletPoints).toHaveLength(3);
    expect(result.extractedBulletPoints[0]).toBe('重构 DOM 节点反查算法');
    expect(result.extractedBulletPoints[1]).toBe('修复流式看门狗超时异常');
    expect(result.extractedBulletPoints[2]).toBe('验证端到端测试门禁');
    expect(result.actionableTitle).toBe('重构 DOM 节点反查算法');
    expect(result.category).toBe('fix');
  });

  it('truncates overly long titles to preserve clean UI presentation', () => {
    const raw =
      '没问题，我们需要执行一个非常非常漫长且具有多个从句的超长标题任务，用于验证前端组件在极端超宽长文本情况下是否能够自动添加省略号并保持工整。本行附加极长的测试文本以确保整体长度绝对超过八十个字符的截断门限。';
    const result = extractCleanedActionItem(raw);
    expect(result.actionableTitle.length).toBeLessThanOrEqual(80);
    expect(result.actionableTitle.endsWith('...')).toBe(true);
  });

  it('infers investigate category for root cause and diagnostic suggestions', () => {
    const raw = '排查沙箱容器内内存泄漏的根本原因并输出诊断指标';
    const result = extractCleanedActionItem(raw);
    expect(result.category).toBe('investigate');
  });

  it('infers verify category for test and assertion suggestions', () => {
    const raw = '编写 Vitest 单测验证所有边界分支';
    const result = extractCleanedActionItem(raw);
    expect(result.category).toBe('verify');
  });
});
