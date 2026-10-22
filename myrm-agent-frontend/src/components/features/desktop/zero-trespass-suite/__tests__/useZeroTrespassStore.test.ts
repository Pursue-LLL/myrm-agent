import { describe, it, expect, beforeEach } from 'vitest';
import { useZeroTrespassStore } from '../useZeroTrespassStore';

describe('useZeroTrespassStore', () => {
  beforeEach(() => {
    useZeroTrespassStore.getState().resetState();
  });

  it('initializes with default zero-trespass denied autostart and neverOverrideSystemChoice = true', () => {
    const state = useZeroTrespassStore.getState();

    expect(state.autostartAuth).toBe('denied');
    expect(state.neverOverrideSystemChoice).toBe(true);
    expect(state.daemonMetrics.pid).toBe(41820);
    expect(state.daemonMetrics.isZombieCleaned).toBe(false);
    expect(state.costBudget.thresholdUsd).toBe(0.50);
    expect(state.physicalTelemetry.isDowngradeDetected).toBe(false);
  });

  it('updates autostart authorization without overriding system protection contract', () => {
    const store = useZeroTrespassStore.getState();

    store.setAutostartAuth('granted');
    expect(useZeroTrespassStore.getState().autostartAuth).toBe('granted');
    expect(useZeroTrespassStore.getState().neverOverrideSystemChoice).toBe(true);

    store.setAutostartAuth('denied');
    expect(useZeroTrespassStore.getState().autostartAuth).toBe('denied');
  });

  it('updates daemon metrics and performs kill and clean on zombie process', () => {
    const store = useZeroTrespassStore.getState();

    store.updateDaemonMetrics({ cpuUsagePercent: 1.2, memoryUsageMb: 72.4 });
    const updated = useZeroTrespassStore.getState().daemonMetrics;
    expect(updated.cpuUsagePercent).toBe(1.2);
    expect(updated.memoryUsageMb).toBe(72.4);

    store.killAndCleanZombieProcess();
    const cleaned = useZeroTrespassStore.getState().daemonMetrics;
    expect(cleaned.cpuUsagePercent).toBe(0);
    expect(cleaned.memoryUsageMb).toBe(0);
    expect(cleaned.isZombieCleaned).toBe(true);
  });

  it('triggers budget confirmation gate when estimated cost exceeds threshold', () => {
    const store = useZeroTrespassStore.getState();

    // 预估成本 $0.20 < $0.50 阈值 -> 不需要闸门确认
    store.setBudgetEstimation(40000, 0.20);
    expect(useZeroTrespassStore.getState().costBudget.isGateConfirmed).toBe(true);

    // 预估成本 $1.20 >= $0.50 阈值 -> 触发闸门阻断
    store.setBudgetEstimation(240000, 1.20);
    expect(useZeroTrespassStore.getState().costBudget.isGateConfirmed).toBe(false);

    // 用户手动确认放行
    store.confirmBudgetGate();
    expect(useZeroTrespassStore.getState().costBudget.isGateConfirmed).toBe(true);
  });

  it('detects model downgrade when physicalModelId does not match claimedModelId', () => {
    const store = useZeroTrespassStore.getState();

    // 正常一致
    store.recordTelemetry({
      physicalModelId: 'claude-3-5-sonnet-20241022',
      claimedModelId: 'claude-3-5-sonnet-20241022',
      provider: 'Anthropic Direct',
      latencyMs: 350,
    });
    expect(useZeroTrespassStore.getState().physicalTelemetry.isDowngradeDetected).toBe(false);

    // 发生暗降欺诈：宣称 Sonnet 实际调度 Haiku
    store.recordTelemetry({
      physicalModelId: 'claude-3-haiku-20240307',
      claimedModelId: 'claude-3-5-sonnet-20241022',
      provider: 'Proxy Node',
      latencyMs: 120,
    });
    expect(useZeroTrespassStore.getState().physicalTelemetry.isDowngradeDetected).toBe(true);
  });

  it('toggles BYOK mode and manages delta OTA status', () => {
    const store = useZeroTrespassStore.getState();
    expect(store.isByokActive).toBe(false);

    store.toggleByok();
    expect(useZeroTrespassStore.getState().isByokActive).toBe(true);

    store.updateDeltaOtaStatus({ status: 'up_to_date', patchSizeKb: 0 });
    expect(useZeroTrespassStore.getState().deltaOta.status).toBe('up_to_date');
    expect(useZeroTrespassStore.getState().deltaOta.patchSizeKb).toBe(0);
  });
});
