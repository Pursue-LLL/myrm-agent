import { describe, it, expect } from 'vitest';
import {
  BUDGET_OPTIONS,
  formatElapsedSec,
  formatThinkingTokens,
  parseReasoningStages,
} from '../reasoningTimelineEngine';

describe('reasoningTimelineEngine', () => {
  it('provides all four budget tier configurations correctly', () => {
    expect(BUDGET_OPTIONS.off.tokenLimit).toBe(0);
    expect(BUDGET_OPTIONS.low.tokenLimit).toBe(1024);
    expect(BUDGET_OPTIONS.medium.tokenLimit).toBe(8192);
    expect(BUDGET_OPTIONS.high.tokenLimit).toBe(32768);
  });

  it('formats elapsed time in seconds and minutes', () => {
    expect(formatElapsedSec(12.4)).toBe('12.4s');
    expect(formatElapsedSec(45.0)).toBe('45.0s');
    expect(formatElapsedSec(84)).toBe('1m 24s');
    expect(formatElapsedSec(135.2)).toBe('2m 15s');
  });

  it('formats thinking token counts accurately', () => {
    expect(formatThinkingTokens(850)).toBe('850');
    expect(formatThinkingTokens(4210)).toBe('4.2k');
    expect(formatThinkingTokens(32000)).toBe('32.0k');
  });

  it('returns empty array for empty reasoning input', () => {
    expect(parseReasoningStages('')).toEqual([]);
    expect(parseReasoningStages('   ')).toEqual([]);
  });

  it('parses explicit stage section headers correctly', () => {
    const rawCoT = `[阶段 1: 业务解构]
分析网关吞吐与连接数限制。
[阶段 2: 方案推演]
比较多线程与异步协程方案。
[阶段 3: 执行落地]
落地基于 Tokio 的事件循环驱动。`;

    const stages = parseReasoningStages(rawCoT, false);
    expect(stages.length).toBe(3);
    expect(stages[0].title).toBe('阶段 1: 业务解构');
    expect(stages[0].status).toBe('completed');
    expect(stages[1].title).toBe('阶段 2: 方案推演');
    expect(stages[2].title).toBe('阶段 3: 执行落地');
  });

  it('marks last stage in-progress during streaming', () => {
    const rawCoT = `[阶段 1: 问题分析]
初步排查死锁原因。
[阶段 2: 方案重构]
正在推导新的锁序协议...`;

    const stages = parseReasoningStages(rawCoT, true);
    expect(stages.length).toBe(2);
    expect(stages[0].status).toBe('completed');
    expect(stages[1].status).toBe('in-progress');
  });

  it('falls back to 3-step natural paragraph semantic deduction', () => {
    const textWithParagraphs = `第一段先梳理系统的核心诉求与性能指标。

第二段权衡本地存储与远程中心化存储的可用性。

第三段最终确定采用本地 WAL 方案并进行落盘验证。`;

    const stages = parseReasoningStages(textWithParagraphs, false);
    expect(stages.length).toBe(3);
    expect(stages[0].title).toContain('阶段 1');
    expect(stages[1].title).toContain('阶段 2');
    expect(stages[2].title).toContain('阶段 3');
  });
});
