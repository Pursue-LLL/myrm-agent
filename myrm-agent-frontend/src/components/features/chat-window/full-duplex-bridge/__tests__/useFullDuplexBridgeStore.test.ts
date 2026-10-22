import { describe, it, expect, beforeEach } from 'vitest';
import { useFullDuplexBridgeStore } from '../useFullDuplexBridgeStore';

describe('useFullDuplexBridgeStore', () => {
  beforeEach(() => {
    useFullDuplexBridgeStore.getState().reset();
  });

  it('spawns a new worker with default steps and correct initial values', () => {
    const store = useFullDuplexBridgeStore.getState();
    const id = store.spawnWorker({
      title: '高耗时代码编译',
      category: '编译构建',
      estimatedTotalSec: 90,
      stepLabels: ['解析 AST', '类型检查', '输出 WASM'],
    });

    const current = useFullDuplexBridgeStore.getState().activeWorkers[id];
    expect(current).toBeDefined();
    expect(current?.title).toBe('高耗时代码编译');
    expect(current?.status).toBe('running');
    expect(current?.progress).toBe(5);
    expect(current?.steps.length).toBe(3);
    expect(current?.steps[0]?.status).toBe('running');
    expect(current?.steps[1]?.status).toBe('pending');
  });

  it('updates worker progress and clamps between 0 and 100', () => {
    const store = useFullDuplexBridgeStore.getState();
    const id = store.spawnWorker({ title: '测试任务' });

    store.updateWorkerProgress(id, 65, '执行中间步');
    let task = useFullDuplexBridgeStore.getState().activeWorkers[id];
    expect(task?.progress).toBe(65);
    expect(task?.currentStepLabel).toBe('执行中间步');

    // 溢出上限检测
    store.updateWorkerProgress(id, 120);
    task = useFullDuplexBridgeStore.getState().activeWorkers[id];
    expect(task?.progress).toBe(100);
    expect(task?.status).toBe('completed');
  });

  it('advances specific step status and details', () => {
    const store = useFullDuplexBridgeStore.getState();
    const id = store.spawnWorker({
      title: '流程任务',
      stepLabels: ['步骤一', '步骤二'],
    });

    store.advanceStep(id, 'step-1', 'completed', '阶段一已就绪');
    store.advanceStep(id, 'step-2', 'running');

    const task = useFullDuplexBridgeStore.getState().activeWorkers[id];
    expect(task?.steps[0]?.status).toBe('completed');
    expect(task?.steps[0]?.detail).toBe('阶段一已就绪');
    expect(task?.steps[1]?.status).toBe('running');
  });

  it('completes worker and creates reanchored result card', () => {
    const store = useFullDuplexBridgeStore.getState();
    const id = store.spawnWorker({ title: '竞品调研' });

    store.completeWorker(id, {
      id: 'art-99',
      title: '调研摘要.md',
      type: 'report',
      summary: '已提取 5 大竞品架构',
    });

    const state = useFullDuplexBridgeStore.getState();
    const task = state.activeWorkers[id];
    expect(task?.status).toBe('completed');
    expect(task?.progress).toBe(100);

    expect(state.reanchoredResults.length).toBe(1);
    expect(state.reanchoredResults[0]?.title).toBe('竞品调研');
    expect(state.reanchoredResults[0]?.artifact.type).toBe('report');
    expect(state.unreadResultCount).toBe(1);
  });

  it('handles failWorker and cancelWorker', () => {
    const store = useFullDuplexBridgeStore.getState();
    const id1 = store.spawnWorker({ title: '失败任务' });
    const id2 = store.spawnWorker({ title: '取消任务' });

    store.failWorker(id1, '网络超时中断');
    store.cancelWorker(id2);

    const workers = useFullDuplexBridgeStore.getState().activeWorkers;
    expect(workers[id1]?.status).toBe('failed');
    expect(workers[id1]?.errorMessage).toBe('网络超时中断');
    expect(workers[id2]?.status).toBe('canceled');
  });

  it('manages tray drawer, adopts, and dismisses results', () => {
    const store = useFullDuplexBridgeStore.getState();
    const id = store.spawnWorker({ title: '成果采纳测试' });
    store.completeWorker(id, {
      id: 'art-1',
      title: '成果',
      type: 'data',
      summary: '测试数据',
    });

    const firstResult = useFullDuplexBridgeStore.getState().reanchoredResults[0];
    expect(firstResult).toBeDefined();
    const resultId = firstResult ? firstResult.id : '';

    store.toggleTrayDrawer(true);
    expect(useFullDuplexBridgeStore.getState().isTrayDrawerOpen).toBe(true);
    expect(useFullDuplexBridgeStore.getState().unreadResultCount).toBe(0);

    store.markResultAdopted(resultId);
    expect(
      useFullDuplexBridgeStore.getState().reanchoredResults[0]?.isAdopted,
    ).toBe(true);

    store.dismissResult(resultId);
    expect(useFullDuplexBridgeStore.getState().reanchoredResults.length).toBe(0);
  });
});
