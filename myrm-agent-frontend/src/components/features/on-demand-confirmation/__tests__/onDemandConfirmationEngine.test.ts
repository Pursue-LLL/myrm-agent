import { describe, it, expect } from 'vitest';
import {
  mapKeyToOptionLetter,
  buildDecisionResult,
  NINE_ENTRY_NAV_ITEMS,
} from '../onDemandConfirmationEngine';
import { ConfirmationOptionItem, OnDemandDecisionInterrupt } from '../onDemandConfirmationTypes';

describe('onDemandConfirmationEngine 核心逻辑单测', () => {
  const options: ConfirmationOptionItem[] = [
    { id: 'A', label: '方案 A：重构模块' },
    { id: 'B', label: '方案 B：保留旧逻辑增量添加' },
    { id: 'C', label: '方案 C：先输出测试用例' },
  ];

  it('mapKeyToOptionLetter 支持数字键 1-3 映射为 A-C，并拦截未定义选项', () => {
    expect(mapKeyToOptionLetter('1', options)).toBe('A');
    expect(mapKeyToOptionLetter('2', options)).toBe('B');
    expect(mapKeyToOptionLetter('3', options)).toBe('C');
    expect(mapKeyToOptionLetter('4', options)).toBeNull(); // 选项只有 A-C
    expect(mapKeyToOptionLetter('9', options)).toBeNull();
  });

  it('mapKeyToOptionLetter 支持字母键 a/b/c 映射为 A/B/C', () => {
    expect(mapKeyToOptionLetter('a', options)).toBe('A');
    expect(mapKeyToOptionLetter('B', options)).toBe('B');
    expect(mapKeyToOptionLetter('c', options)).toBe('C');
    expect(mapKeyToOptionLetter('d', options)).toBeNull();
  });

  it('buildDecisionResult 能正确组装决策结果与补充说明', () => {
    const interrupt: OnDemandDecisionInterrupt = {
      interruptId: 'int-101',
      taskId: 'task-777',
      prompt: '请选择代码重构方案',
      options,
    };

    const result = buildDecisionResult(interrupt, 'A', '注意保证向后兼容性');
    expect(result.interruptId).toBe('int-101');
    expect(result.taskId).toBe('task-777');
    expect(result.selectedOptionId).toBe('A');
    expect(result.selectedOptionLabel).toBe('方案 A：重构模块');
    expect(result.customInput).toBe('注意保证向后兼容性');
    expect(result.decidedAt).toBeDefined();
  });

  it('NINE_ENTRY_NAV_ITEMS 包含 9 个完整入口且涵盖三种分类', () => {
    expect(NINE_ENTRY_NAV_ITEMS.length).toBe(9);
    const categories = new Set(NINE_ENTRY_NAV_ITEMS.map((item) => item.category));
    expect(categories.has('lifecycle')).toBe(true);
    expect(categories.has('collaboration')).toBe(true);
    expect(categories.has('assets')).toBe(true);
  });
});
