import { describe, it, expect, beforeEach } from 'vitest';
import { useSandboxDualViewportStore } from '../useSandboxDualViewportStore';

describe('useSandboxDualViewportStore', () => {
  beforeEach(() => {
    useSandboxDualViewportStore.getState().resetState();
  });

  it('initializes with default desktop mode and default design assets', () => {
    const state = useSandboxDualViewportStore.getState();

    expect(state.activeMode).toBe('desktop');
    expect(state.targetPreviewUrl).toBe('http://localhost:5173/preview');
    expect(state.consoleErrors).toHaveLength(0);
    expect(state.networkAnomalies).toHaveLength(0);
    expect(state.designAssets).toHaveLength(3);
    expect(state.healingCycle.status).toBe('idle');
  });

  it('updates activeMode and preview url correctly', () => {
    const store = useSandboxDualViewportStore.getState();

    store.setActiveMode('mobile');
    expect(useSandboxDualViewportStore.getState().activeMode).toBe('mobile');

    store.setActiveMode('side_by_side');
    expect(useSandboxDualViewportStore.getState().activeMode).toBe('side_by_side');

    store.setTargetPreviewUrl('http://localhost:3000');
    expect(useSandboxDualViewportStore.getState().targetPreviewUrl).toBe('http://localhost:3000');
  });

  it('adds, records, and clears console errors and network anomalies', () => {
    const store = useSandboxDualViewportStore.getState();

    store.addConsoleLog({
      level: 'error',
      message: 'Uncaught TypeError: Cannot read properties of undefined (reading "title")',
      stack: 'TypeError: Cannot read properties of undefined at TableRow.tsx:42',
    });

    store.addNetworkAnomaly({
      url: '/api/v1/user/avatar.png',
      method: 'GET',
      status: 404,
      statusText: 'Not Found',
    });

    const state = useSandboxDualViewportStore.getState();
    expect(state.consoleErrors).toHaveLength(1);
    expect(state.consoleErrors[0]?.message).toContain('TypeError');
    expect(state.networkAnomalies).toHaveLength(1);
    expect(state.networkAnomalies[0]?.status).toBe(404);

    // 测试清空
    store.clearConsoleLogs();
    store.clearNetworkAnomalies();
    expect(useSandboxDualViewportStore.getState().consoleErrors).toHaveLength(0);
    expect(useSandboxDualViewportStore.getState().networkAnomalies).toHaveLength(0);
  });

  it('toggles design system asset enforcement', () => {
    const store = useSandboxDualViewportStore.getState();
    const tableAsset = store.designAssets.find((a) => a.id === 'ds-table');
    expect(tableAsset?.isEnforced).toBe(true);

    store.toggleAssetEnforcement('ds-table');
    const updatedTable = useSandboxDualViewportStore.getState().designAssets.find((a) => a.id === 'ds-table');
    expect(updatedTable?.isEnforced).toBe(false);

    store.toggleAssetEnforcement('ds-table');
    const reEnabled = useSandboxDualViewportStore.getState().designAssets.find((a) => a.id === 'ds-table');
    expect(reEnabled?.isEnforced).toBe(true);
  });

  it('manages self-healing lifecycle from injection to recompilation to verified clean', () => {
    const store = useSandboxDualViewportStore.getState();

    // 1. 无错误时触发直接 verified
    store.triggerSelfHealing();
    expect(useSandboxDualViewportStore.getState().healingCycle.status).toBe('healed_verified');

    // 2. 注入错误
    store.addConsoleLog({
      level: 'error',
      message: 'Uncaught ReferenceError: process is not defined',
    });

    store.triggerSelfHealing();
    const activeCycle = useSandboxDualViewportStore.getState().healingCycle;
    expect(activeCycle.status).toBe('healing_prompt_injected');
    expect(activeCycle.detectedErrorsCount).toBe(1);
    expect(activeCycle.lastErrorSummary).toContain('ReferenceError');
    expect(activeCycle.iteration).toBe(1);

    // 3. 推进迭代 -> recompiling
    store.advanceHealingIteration();
    expect(useSandboxDualViewportStore.getState().healingCycle.status).toBe('recompiling');
    expect(useSandboxDualViewportStore.getState().healingCycle.iteration).toBe(2);

    // 4. 验证成功
    store.markHealingSuccess();
    const healedState = useSandboxDualViewportStore.getState();
    expect(healedState.healingCycle.status).toBe('healed_verified');
    expect(healedState.consoleErrors).toHaveLength(0);
  });

  it('transitions to healing_exhausted when iteration exceeds limit', () => {
    const store = useSandboxDualViewportStore.getState();

    store.addConsoleLog({ level: 'error', message: 'Persistent SyntaxError' });
    store.triggerSelfHealing(); // iteration 1

    store.advanceHealingIteration(); // iteration 2
    store.advanceHealingIteration(); // iteration 3
    store.advanceHealingIteration(); // exceeds max (3) -> healing_exhausted

    expect(useSandboxDualViewportStore.getState().healingCycle.status).toBe('healing_exhausted');
  });
});
