import { beforeEach, describe, expect, it } from 'vitest';
import { useDualTrackStore } from '../useDualTrackStore';
import type { EngineeringTraceDetails } from '../dualTrackTypes';

describe('useDualTrackStore', () => {
  beforeEach(() => {
    useDualTrackStore.getState().resetAll();
  });

  it('初始状态为业务极简模式且抽屉关闭', () => {
    const state = useDualTrackStore.getState();
    expect(state.viewMode).toBe('business');
    expect(state.isTraceDrawerOpen).toBe(false);
    expect(state.activeTraceDetails).toBeNull();
  });

  it('支持切换视图模式', () => {
    const store = useDualTrackStore.getState();
    store.setViewMode('engineering');
    expect(useDualTrackStore.getState().viewMode).toBe('engineering');

    store.toggleViewMode();
    expect(useDualTrackStore.getState().viewMode).toBe('business');
  });

  it('支持打开与关闭底层工程追踪抽屉', () => {
    const trace: EngineeringTraceDetails = {
      turnId: 'turn-999',
      toolCalls: [],
      codeDiffs: [],
      terminalLogs: ['Done'],
      testAssertions: [],
      timestamp: Date.now(),
    };

    useDualTrackStore.getState().openTraceDrawer(trace);
    expect(useDualTrackStore.getState().isTraceDrawerOpen).toBe(true);
    expect(useDualTrackStore.getState().activeTraceDetails?.turnId).toBe(
      'turn-999'
    );

    useDualTrackStore.getState().closeTraceDrawer();
    expect(useDualTrackStore.getState().isTraceDrawerOpen).toBe(false);
    expect(useDualTrackStore.getState().activeTraceDetails).toBeNull();
  });

  it('支持为指定智能体配置并应用默认视图偏好', () => {
    useDualTrackStore.getState().setAgentPreference('code-architect', 'engineering');
    useDualTrackStore.getState().setAgentPreference('business-advisor', 'business');

    useDualTrackStore.getState().applyAgentPreference('code-architect');
    expect(useDualTrackStore.getState().viewMode).toBe('engineering');

    useDualTrackStore.getState().applyAgentPreference('business-advisor');
    expect(useDualTrackStore.getState().viewMode).toBe('business');
  });
});
