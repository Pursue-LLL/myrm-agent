import { describe, expect, it } from 'vitest';
import {
  calculatePlanProgress,
  formatElapsedTimeString,
  formatProgressHudLabel,
  toggleSubtaskSkipState,
  updateSubtaskStatus,
  validateMicroPlanDraft,
} from '../companionPlanHubEngine';
import type { PlanSubtaskItem } from '../companionPlanHubTypes';

describe('companionPlanHubEngine', () => {
  it('正确计算任务计划书进度与百分比', () => {
    const empty = calculatePlanProgress([]);
    expect(empty.percent).toBe(100);
    expect(empty.isAllDone).toBe(true);

    const subtasks: PlanSubtaskItem[] = [
      { id: '1', title: '任务1', status: 'completed', required: true, order: 1 },
      { id: '2', title: '任务2', status: 'skipped', required: false, order: 2 },
      { id: '3', title: '任务3', status: 'pending', required: false, order: 3 },
    ];

    const progress = calculatePlanProgress(subtasks);
    expect(progress.total).toBe(3);
    expect(progress.completed).toBe(1);
    expect(progress.skipped).toBe(1);
    expect(progress.percent).toBe(50); // 1 / (3 - 1) = 50%
    expect(progress.isAllDone).toBe(false);
  });

  it('格式化步骤进度抬头显示标签', () => {
    const label = formatProgressHudLabel(2, 5, '正在生成店长端经营图表');
    expect(label).toBe('正在生成店长端经营图表 (2/5)');

    const outOfBounds = formatProgressHudLabel(10, 5, '边界测试');
    expect(outOfBounds).toBe('边界测试 (5/5)');
  });

  it('切换子任务跳过状态并保护必选任务', () => {
    const subtasks: PlanSubtaskItem[] = [
      { id: 't1', title: '核心需求对齐', status: 'pending', required: true, order: 1 },
      { id: 't2', title: '生成原型图', status: 'pending', required: false, order: 2 },
    ];

    // 必选任务不可跳过
    const afterTrySkipReq = toggleSubtaskSkipState(subtasks, 't1');
    expect(afterTrySkipReq[0].status).toBe('pending');

    // 非必选任务可以跳过
    const afterSkipOpt = toggleSubtaskSkipState(subtasks, 't2');
    expect(afterSkipOpt[1].status).toBe('skipped');

    // 再次点击恢复为 pending
    const restored = toggleSubtaskSkipState(afterSkipOpt, 't2');
    expect(restored[1].status).toBe('pending');
  });

  it('更新指定子任务状态', () => {
    const subtasks: PlanSubtaskItem[] = [
      { id: 't1', title: '任务1', status: 'pending', required: false, order: 1 },
    ];
    const updated = updateSubtaskStatus(subtasks, 't1', 'in_progress');
    expect(updated[0].status).toBe('in_progress');
  });

  it('格式化已耗时字符串为 mm:ss 格式', () => {
    expect(formatElapsedTimeString(0)).toBe('00:00');
    expect(formatElapsedTimeString(45)).toBe('00:45');
    expect(formatElapsedTimeString(125)).toBe('02:05');
  });

  it('校验并解析计划草案合法性', () => {
    const invalid = validateMicroPlanDraft(null);
    expect(invalid.valid).toBe(false);

    const missingGoal = validateMicroPlanDraft({ planId: 'p1' });
    expect(missingGoal.valid).toBe(false);

    const validRaw = {
      planId: 'plan-1',
      goal: '自动化巡检',
      subtasks: [
        { id: 's1', title: '巡检1', status: 'pending', required: true },
      ],
      estimatedMinutes: 10,
    };
    const valid = validateMicroPlanDraft(validRaw);
    expect(valid.valid).toBe(true);
    expect(valid.plan?.planId).toBe('plan-1');
    expect(valid.plan?.subtasks.length).toBe(1);
    expect(valid.plan?.targetAgentName).toBe('Myrm 调度助手');
  });
});
