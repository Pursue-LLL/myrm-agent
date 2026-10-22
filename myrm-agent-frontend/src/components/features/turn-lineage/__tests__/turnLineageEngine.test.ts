import { describe, it, expect } from 'vitest';
import {
  getOriginVisualTheme,
  filterTurns,
  traceCausalityLineage,
  getDefaultTurns,
} from '../turnLineageEngine';

describe('turnLineageEngine', () => {
  it('getOriginVisualTheme 应正确返回 5 类触发源的视觉配置', () => {
    const userTheme = getOriginVisualTheme('user_direct');
    expect(userTheme.label).toBe('人工直接指令');

    const cronTheme = getOriginVisualTheme('cron_job');
    expect(cronTheme.label).toBe('定时调度任务');
    expect(cronTheme.badgeBg).toContain('purple');

    const webhookTheme = getOriginVisualTheme('webhook_trigger');
    expect(webhookTheme.label).toBe('外部 Webhook');

    const subagentTheme = getOriginVisualTheme('subagent_delegation');
    expect(subagentTheme.label).toBe('智能体移交');

    const approvalTheme = getOriginVisualTheme('approval_resume');
    expect(approvalTheme.label).toBe('审批放行恢复');
  });

  it('filterTurns 应按审计模式精确筛选对应轮次', () => {
    const turns = getDefaultTurns();

    const allTurns = filterTurns(turns, 'all');
    expect(allTurns.length).toBe(turns.length);

    const userOnly = filterTurns(turns, 'user_only');
    expect(userOnly.length).toBeGreaterThan(0);
    expect(userOnly.every((t) => t.provenance.originType === 'user_direct')).toBe(true);

    const automatedOnly = filterTurns(turns, 'automated_only');
    expect(
      automatedOnly.every(
        (t) =>
          t.provenance.originType === 'cron_job' ||
          t.provenance.originType === 'webhook_trigger'
      )
    ).toBe(true);

    const handoffOnly = filterTurns(turns, 'handoff_only');
    expect(
      handoffOnly.every(
        (t) =>
          t.provenance.originType === 'subagent_delegation' ||
          t.provenance.originType === 'approval_resume'
      )
    ).toBe(true);
  });

  it('traceCausalityLineage 应沿 causalityParentId 追溯因果关系祖先链', () => {
    const turns = getDefaultTurns();

    // turn-5 的父级是 turn-4，turn-4 的父级是 turn-3
    const chain = traceCausalityLineage('turn-5', turns);
    expect(chain).toEqual(['turn-3', 'turn-4', 'turn-5']);

    // 无父级的独立轮次
    const singleChain = traceCausalityLineage('turn-1', turns);
    expect(singleChain).toEqual(['turn-1']);
  });

  it('getDefaultTurns 应返回结构完整的真实多源协同会话流', () => {
    const turns = getDefaultTurns();
    expect(turns.length).toBeGreaterThanOrEqual(6);
    expect(turns[0]).toHaveProperty('id');
    expect(turns[0]).toHaveProperty('provenance');
    expect(turns[0].provenance).toHaveProperty('originType');
    expect(turns[0].provenance).toHaveProperty('triggerSourceTitle');
  });
});
