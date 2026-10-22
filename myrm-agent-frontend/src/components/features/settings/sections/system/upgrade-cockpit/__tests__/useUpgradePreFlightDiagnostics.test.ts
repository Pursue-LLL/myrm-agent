import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useUpgradePreFlightDiagnostics } from '../useUpgradePreFlightDiagnostics';

describe('useUpgradePreFlightDiagnostics', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('initializes with default multi-mirror probes and recommends CNB mirror', () => {
    const { result } = renderHook(() => useUpgradePreFlightDiagnostics());

    expect(result.current.mirrorProbes).toHaveLength(4);
    const cnbMirror = result.current.mirrorProbes.find((p) => p.id === 'cnb');
    expect(cnbMirror?.isRecommended).toBe(true);
    expect(cnbMirror?.status).toBe('optimal');
    expect(result.current.currentStage).toBe('idle');
  });

  it('runs preflight network latency diagnostics and updates probe status', async () => {
    const { result } = renderHook(() => useUpgradePreFlightDiagnostics());

    let probePromise: Promise<void>;
    act(() => {
      probePromise = result.current.runPreFlightProbes();
    });

    expect(result.current.isProbing).toBe(true);

    await act(async () => {
      vi.advanceTimersByTime(100);
      await probePromise;
    });

    expect(result.current.isProbing).toBe(false);
    const githubMirror = result.current.mirrorProbes.find((p) => p.id === 'github');
    expect(githubMirror?.status).toBe('degraded');
  });

  it('detects active tasks and provides safe drain recommendation', async () => {
    const { result } = renderHook(() => useUpgradePreFlightDiagnostics());

    // 1. 系统空闲时安全判定
    await act(async () => {
      await result.current.checkActiveTaskSafety(false);
    });
    expect(result.current.activeTaskSafety.recommendation).toBe('safe_to_reload');
    expect(result.current.activeTaskSafety.hasActiveGoal).toBe(false);

    // 2. 检测到正在运行的长程 Goal 时的防误杀拦截判定
    await act(async () => {
      await result.current.checkActiveTaskSafety(true);
    });
    expect(result.current.activeTaskSafety.hasActiveGoal).toBe(true);
    expect(result.current.activeTaskSafety.recommendation).toBe('drain_first');
    expect(result.current.activeTaskSafety.activeTasks).toHaveLength(1);
  });

  it('executes 5-stage dual-instance pipeline to completion and supports rollback', async () => {
    const { result } = renderHook(() => useUpgradePreFlightDiagnostics());

    let pipelinePromise: Promise<void>;
    act(() => {
      pipelinePromise = result.current.startUpgradePipeline({ mirrorId: 'cnb' });
    });

    expect(result.current.isModalOpen).toBe(true);

    // 推进 5 个阶段的耗时
    await act(async () => {
      await vi.runAllTimersAsync();
      await pipelinePromise;
    });

    expect(result.current.currentStage).toBe('complete');

    // 测试 1 秒原子回滚
    let rollbackPromise: Promise<void>;
    act(() => {
      rollbackPromise = result.current.rollbackImmediate();
    });

    await act(async () => {
      await vi.runAllTimersAsync();
      await rollbackPromise;
    });

    expect(result.current.currentStage).toBe('rolled_back');
  });
});
