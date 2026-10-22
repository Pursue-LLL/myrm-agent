import { beforeEach, describe, expect, it } from 'vitest';
import { useSwarmCanvasStore } from '../useSwarmCanvasStore';
import type { SwarmWorkerItem } from '../swarmCanvasTypes';

describe('useSwarmCanvasStore', () => {
  const mockWorkers: SwarmWorkerItem[] = [
    {
      id: 'w-1',
      name: '测试智能体1',
      role: '测试',
      colorTheme: '#3b82f6',
      status: 'idle',
      currentTaskTitle: '任务1',
      progressPercent: 0,
      thinkingLogs: [],
      toolCalls: [],
      createdAt: Date.now(),
    },
  ];

  beforeEach(() => {
    useSwarmCanvasStore.getState().resetAll();
  });

  it('初始状态合规且支持重置', () => {
    const state = useSwarmCanvasStore.getState();
    expect(state.workers.length).toBe(0);
    expect(state.focusedWorkerId).toBeNull();
    expect(state.isLensDrawerOpen).toBe(false);
    expect(state.statusFilter).toBe('all');
  });

  it('支持设置智能体列表与更新特定智能体状态', () => {
    useSwarmCanvasStore.getState().setWorkers(mockWorkers);
    expect(useSwarmCanvasStore.getState().workers.length).toBe(1);

    useSwarmCanvasStore.getState().updateWorker('w-1', {
      status: 'running',
      progressPercent: 45,
    });

    const updated = useSwarmCanvasStore.getState().workers[0];
    expect(updated.status).toBe('running');
    expect(updated.progressPercent).toBe(45);
  });

  it('支持聚焦特定智能体并打开聚焦透镜抽屉', () => {
    useSwarmCanvasStore.getState().setWorkers(mockWorkers);
    useSwarmCanvasStore.getState().focusWorker('w-1');

    expect(useSwarmCanvasStore.getState().focusedWorkerId).toBe('w-1');
    expect(useSwarmCanvasStore.getState().isLensDrawerOpen).toBe(true);

    useSwarmCanvasStore.getState().closeLens();
    expect(useSwarmCanvasStore.getState().isLensDrawerOpen).toBe(false);
    expect(useSwarmCanvasStore.getState().focusedWorkerId).toBeNull();
  });

  it('支持向特定子智能体派发人工纠偏指令 (steer)', () => {
    useSwarmCanvasStore.getState().setWorkers(mockWorkers);
    useSwarmCanvasStore.getState().steerWorker('w-1', '请重点排查并发死锁');

    const worker = useSwarmCanvasStore.getState().workers[0];
    expect(worker.status).toBe('running');
    expect(worker.thinkingLogs).toContain(
      '[人工纠偏] 收到用户指令: 请重点排查并发死锁'
    );
  });

  it('支持手动叫停特定智能体', () => {
    useSwarmCanvasStore.getState().setWorkers(mockWorkers);
    useSwarmCanvasStore.getState().stopWorker('w-1');

    const worker = useSwarmCanvasStore.getState().workers[0];
    expect(worker.status).toBe('failed');
    expect(worker.thinkingLogs).toContain('[用户干预] 已手动终止此子任务');
  });
});
