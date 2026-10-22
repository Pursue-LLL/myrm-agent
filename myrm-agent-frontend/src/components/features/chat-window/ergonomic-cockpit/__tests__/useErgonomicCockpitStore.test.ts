import { describe, it, expect, beforeEach } from 'vitest';
import { useErgonomicCockpitStore } from '../useErgonomicCockpitStore';

describe('useErgonomicCockpitStore', () => {
  beforeEach(() => {
    useErgonomicCockpitStore.getState().resetState();
  });

  it('initializes with default wide_ergonomic mode and default decoupled gait', () => {
    const state = useErgonomicCockpitStore.getState();

    expect(state.viewportMode).toBe('wide_ergonomic');
    expect(state.isSidePanelsCollapsed).toBe(false);
    expect(state.activePersona.name).toBe('首席全栈架构师');
    expect(state.activePersona.state).toBe('thinking');

    expect(state.currentGait).not.toBeNull();
    expect(state.currentGait?.isDecoupledFromInput).toBe(true);
    expect(state.currentGait?.percentage).toBe(60);
  });

  it('switches viewportMode between compact, standard, wide_ergonomic, and ultrawide', () => {
    const store = useErgonomicCockpitStore.getState();

    store.setViewportMode('compact');
    expect(useErgonomicCockpitStore.getState().viewportMode).toBe('compact');

    store.setViewportMode('ultrawide');
    expect(useErgonomicCockpitStore.getState().viewportMode).toBe('ultrawide');

    store.setViewportMode('standard');
    expect(useErgonomicCockpitStore.getState().viewportMode).toBe('standard');
  });

  it('updates agent waveform state correctly', () => {
    const store = useErgonomicCockpitStore.getState();

    store.setAgentWaveformState('tool_executing');
    expect(useErgonomicCockpitStore.getState().activePersona.state).toBe('tool_executing');

    store.setAgentWaveformState('streaming');
    expect(useErgonomicCockpitStore.getState().activePersona.state).toBe('streaming');

    store.setAgentWaveformState('completed');
    expect(useErgonomicCockpitStore.getState().activePersona.state).toBe('completed');
  });

  it('updates gait progress and always enforces isDecoupledFromInput = true', () => {
    const store = useErgonomicCockpitStore.getState();

    store.updateTaskGaitProgress({
      currentStep: 4,
      totalSteps: 5,
      stepTitle: '正在执行产物对齐与渲染...',
      percentage: 80,
    });

    const gait = useErgonomicCockpitStore.getState().currentGait;
    expect(gait).not.toBeNull();
    expect(gait?.currentStep).toBe(4);
    expect(gait?.percentage).toBe(80);
    expect(gait?.stepTitle).toBe('正在执行产物对齐与渲染...');
    expect(gait?.isDecoupledFromInput).toBe(true);

    // 测试清空
    store.updateTaskGaitProgress(null);
    expect(useErgonomicCockpitStore.getState().currentGait).toBeNull();
  });

  it('toggles side panels for foveal centric focus', () => {
    const store = useErgonomicCockpitStore.getState();

    expect(store.isSidePanelsCollapsed).toBe(false);

    store.toggleSidePanels();
    expect(useErgonomicCockpitStore.getState().isSidePanelsCollapsed).toBe(true);

    store.toggleSidePanels(false);
    expect(useErgonomicCockpitStore.getState().isSidePanelsCollapsed).toBe(false);
  });

  it('resets state back to default initial state', () => {
    const store = useErgonomicCockpitStore.getState();

    store.setViewportMode('compact');
    store.toggleSidePanels(true);
    store.updateTaskGaitProgress(null);

    store.resetState();

    const resetState = useErgonomicCockpitStore.getState();
    expect(resetState.viewportMode).toBe('wide_ergonomic');
    expect(resetState.isSidePanelsCollapsed).toBe(false);
    expect(resetState.currentGait).not.toBeNull();
  });
});
