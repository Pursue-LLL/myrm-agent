import { describe, it, expect, beforeEach } from 'vitest';
import { useGracefulDegradationStore } from '../useGracefulDegradationStore';
import {
  ComponentHealthRecord,
  DegradationEvent,
} from '../gracefulDegradationTypes';

describe('useGracefulDegradationStore', () => {
  beforeEach(() => {
    useGracefulDegradationStore.getState().reset();
  });

  it('initializes with empty state after reset and registers new component', () => {
    const record: ComponentHealthRecord = {
      id: 'comp-test',
      name: '测试模型通道',
      type: 'model',
      status: 'closed',
      latencyMs: 180,
      errorRatePercent: 0,
      lastCheckedAt: Date.now(),
      fallbackStrategy: '本地缓存容灾',
    };

    useGracefulDegradationStore.getState().registerOrUpdateComponent(record);

    const comp = useGracefulDegradationStore.getState().components['comp-test'];
    expect(comp).toBeDefined();
    expect(comp?.name).toBe('测试模型通道');
    expect(comp?.latencyMs).toBe(180);
  });

  it('triggers and resolves degradation events correctly', () => {
    const event: DegradationEvent = {
      id: 'deg-001',
      componentId: 'comp-search',
      componentName: '网络检索',
      severity: 'warning',
      title: '检索超时降级',
      explanation: '外部搜索接口超时，切入本地事实知识',
      fallbackActive: true,
      fallbackActionLabel: '已切换本地知识',
      recoveryEtaSec: 30,
      timestamp: Date.now(),
    };

    useGracefulDegradationStore.getState().triggerDegradation(event);
    let active = useGracefulDegradationStore.getState().activeDegradations['deg-001'];
    expect(active).toBeDefined();
    expect(active?.title).toBe('检索超时降级');

    useGracefulDegradationStore.getState().resolveDegradation('deg-001');
    active = useGracefulDegradationStore.getState().activeDegradations['deg-001'];
    expect(active).toBeUndefined();
  });

  it('toggles health modal status properly', () => {
    expect(
      useGracefulDegradationStore.getState().isHealthIndicatorModalOpen,
    ).toBe(false);

    useGracefulDegradationStore.getState().toggleHealthModal(true);
    expect(
      useGracefulDegradationStore.getState().isHealthIndicatorModalOpen,
    ).toBe(true);

    useGracefulDegradationStore.getState().toggleHealthModal(false);
    expect(
      useGracefulDegradationStore.getState().isHealthIndicatorModalOpen,
    ).toBe(false);

    useGracefulDegradationStore.getState().toggleHealthModal();
    expect(
      useGracefulDegradationStore.getState().isHealthIndicatorModalOpen,
    ).toBe(true);
  });
});
