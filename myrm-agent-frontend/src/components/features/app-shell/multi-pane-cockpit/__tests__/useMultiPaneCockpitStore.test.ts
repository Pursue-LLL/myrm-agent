import { describe, it, expect, beforeEach } from 'vitest';
import { useMultiPaneCockpitStore } from '../useMultiPaneCockpitStore';

describe('useMultiPaneCockpitStore', () => {
  beforeEach(() => {
    useMultiPaneCockpitStore.getState().resetCockpitState();
  });

  it('initializes with default three_pane mode and bot list', () => {
    const state = useMultiPaneCockpitStore.getState();
    expect(state.paneMode).toBe('three_pane');
    expect(state.bots.length).toBeGreaterThanOrEqual(4);
    expect(state.selectedBotId).toBe('bot_morning_wechat');
    expect(state.isRosterCollapsed).toBe(false);
    expect(state.isCronInspectorOpen).toBe(true);
    expect(state.isArtifactInspectorOpen).toBe(false);
  });

  it('switches pane mode correctly', () => {
    useMultiPaneCockpitStore.getState().setPaneMode('four_pane');
    let state = useMultiPaneCockpitStore.getState();
    expect(state.paneMode).toBe('four_pane');
    expect(state.isArtifactInspectorOpen).toBe(true);

    useMultiPaneCockpitStore.getState().setPaneMode('two_pane');
    state = useMultiPaneCockpitStore.getState();
    expect(state.paneMode).toBe('two_pane');
    expect(state.isCronInspectorOpen).toBe(false);
  });

  it('selects bot and collapses roster', () => {
    useMultiPaneCockpitStore.getState().selectBot('bot_code_auditor');
    expect(useMultiPaneCockpitStore.getState().selectedBotId).toBe('bot_code_auditor');

    useMultiPaneCockpitStore.getState().toggleRosterCollapse();
    expect(useMultiPaneCockpitStore.getState().isRosterCollapsed).toBe(true);
  });

  it('toggles cron and artifact inspector panels', () => {
    useMultiPaneCockpitStore.getState().toggleCronInspector(false);
    expect(useMultiPaneCockpitStore.getState().isCronInspectorOpen).toBe(false);

    useMultiPaneCockpitStore.getState().toggleCronInspector(true);
    expect(useMultiPaneCockpitStore.getState().isCronInspectorOpen).toBe(true);

    useMultiPaneCockpitStore.getState().toggleArtifactInspector(true);
    expect(useMultiPaneCockpitStore.getState().isArtifactInspectorOpen).toBe(true);
  });

  it('triggers bot pulse activity', () => {
    useMultiPaneCockpitStore.getState().triggerBotPulse('bot_code_auditor', {
      isActive: true,
      activityType: 'active_tool_exec',
      currentTaskTitle: '正在执行 AST 代码合规性检查...',
      progressPercent: 60,
    });

    const bot = useMultiPaneCockpitStore.getState().bots.find((b) => b.id === 'bot_code_auditor');
    expect(bot?.pulse.isActive).toBe(true);
    expect(bot?.pulse.activityType).toBe('active_tool_exec');
    expect(bot?.pulse.progressPercent).toBe(60);
  });

  it('toggles bot cron jobs', () => {
    useMultiPaneCockpitStore.getState().toggleBotCronJob('bot_morning_wechat', 'cron_wechat_morning', false);
    const bot = useMultiPaneCockpitStore.getState().bots.find((b) => b.id === 'bot_morning_wechat');
    const job = bot?.cronJobs.find((j) => j.id === 'cron_wechat_morning');
    expect(job?.isEnabled).toBe(false);
  });

  it('performs handoff to bot session', () => {
    useMultiPaneCockpitStore.getState().handoffToBotSession('bot_deep_researcher');
    const state = useMultiPaneCockpitStore.getState();
    expect(state.selectedBotId).toBe('bot_deep_researcher');
    expect(state.activeHandoffBotId).toBe('bot_deep_researcher');
  });
});
