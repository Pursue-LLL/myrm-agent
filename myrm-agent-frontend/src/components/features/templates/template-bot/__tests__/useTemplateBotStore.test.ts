import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useTemplateBotStore } from '../useTemplateBotStore';

describe('useTemplateBotStore', () => {
  beforeEach(() => {
    useTemplateBotStore.getState().resetToDefaults();
    vi.restoreAllMocks();
  });

  it('初始状态具备默认值且未激活 P0 模式', () => {
    const state = useTemplateBotStore.getState();
    expect(state.isMarketplaceModalOpen).toBe(false);
    expect(state.selectedCategory).toBe('all');
    expect(state.searchKeyword).toBe('');
    expect(state.instantiatedBotIds).toHaveLength(0);
    expect(state.clonedTeamRosters).toHaveLength(0);
    expect(state.p0CruiseState.isActive).toBe(false);
    expect(state.p0CruiseState.urgencyLevel).toBe('normal');
  });

  it('单岗位实例化与自动去重', () => {
    useTemplateBotStore.getState().instantiateBot('bot-chief-of-staff');
    expect(useTemplateBotStore.getState().instantiatedBotIds).toEqual([
      'bot-chief-of-staff',
    ]);

    // 重复实例化不会产生重复元素
    useTemplateBotStore.getState().instantiateBot('bot-chief-of-staff');
    expect(useTemplateBotStore.getState().instantiatedBotIds).toEqual([
      'bot-chief-of-staff',
    ]);
  });

  it('一键克隆团队架构能够批量实例化全部协同岗位', () => {
    const result = useTemplateBotStore
      .getState()
      .cloneTeamRoster('team-tech-delivery');

    expect(result).toBeDefined();
    expect(result?.teamId).toBe('team-tech-delivery');
    expect(result?.instantiatedBotIds.length).toBe(4);

    const state = useTemplateBotStore.getState();
    expect(state.clonedTeamRosters).toHaveLength(1);
    expect(state.instantiatedBotIds).toContain('bot-chief-of-staff');
    expect(state.instantiatedBotIds).toContain('bot-senior-architect');
    expect(state.instantiatedBotIds).toContain('bot-fullstack-engineer');
    expect(state.instantiatedBotIds).toContain('bot-qa-director');
  });

  it('激活 P0 紧急模式能够更新状态机并派发全局事件', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    useTemplateBotStore
      .getState()
      .activateP0UrgencyMode('task-outage-01', '线上支付网关宕机应急抢修');

    const state = useTemplateBotStore.getState();
    expect(state.p0CruiseState.isActive).toBe(true);
    expect(state.p0CruiseState.taskId).toBe('task-outage-01');
    expect(state.p0CruiseState.taskTitle).toBe('线上支付网关宕机应急抢修');
    expect(state.p0CruiseState.urgencyLevel).toBe('p0_urgent');
    expect(state.p0CruiseState.nextInspectionCountdownSeconds).toBe(300);

    expect(dispatchSpy).toHaveBeenCalled();
    const event = dispatchSpy.mock.calls.find(
      (call) => (call[0] as CustomEvent).type === 'myrm:p0-urgency-activated'
    );
    expect(event).toBeDefined();
    if (event) {
      const customEvent = event[0] as CustomEvent;
      expect(customEvent.detail.taskId).toBe('task-outage-01');
    }
  });

  it('看门狗审查发现偏离能够自动记录日志并派发 myrm:p0-steering-injected 事件', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    useTemplateBotStore.getState().activateP0UrgencyMode('task-p0-test');

    const loopingTurns = [
      'tool_call: check_logs',
      'tool_call: check_logs',
      'tool_call: check_logs',
    ];

    useTemplateBotStore.getState().runWatchdogInspection(loopingTurns);

    const state = useTemplateBotStore.getState();
    expect(state.p0CruiseState.deviationInterceptCount).toBe(1);
    expect(state.p0CruiseState.steeringInjectedCount).toBe(1);
    expect(state.p0CruiseState.watchdogLogs).toHaveLength(1);
    expect(state.p0CruiseState.watchdogLogs[0].status).toBe('steered');

    expect(dispatchSpy).toHaveBeenCalled();
    const steeringEvent = dispatchSpy.mock.calls.find(
      (call) => (call[0] as CustomEvent).type === 'myrm:p0-steering-injected'
    );
    expect(steeringEvent).toBeDefined();
  });

  it('倒计时推进并在归零时自动触发看门狗巡检', () => {
    useTemplateBotStore.getState().activateP0UrgencyMode('task-timer-test');

    useTemplateBotStore.getState().tickCountdown();
    expect(
      useTemplateBotStore.getState().p0CruiseState
        .nextInspectionCountdownSeconds
    ).toBe(299);
  });

  it('退出 P0 紧急模式能够恢复正常状态', () => {
    useTemplateBotStore.getState().activateP0UrgencyMode('task-01');
    expect(useTemplateBotStore.getState().p0CruiseState.isActive).toBe(true);

    useTemplateBotStore.getState().deactivateP0UrgencyMode();
    expect(useTemplateBotStore.getState().p0CruiseState.isActive).toBe(false);
    expect(useTemplateBotStore.getState().p0CruiseState.urgencyLevel).toBe(
      'normal'
    );
  });
});
