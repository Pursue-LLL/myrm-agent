import { describe, it, expect, beforeEach } from 'vitest';
import { useTtftDecouplingStore } from '../useTtftDecouplingStore';

describe('useTtftDecouplingStore', () => {
  beforeEach(() => {
    useTtftDecouplingStore.getState().reset();
  });

  it('emits early ack with default intent summary and speculative tools', () => {
    const store = useTtftDecouplingStore.getState();
    const ackId = store.emitEarlyAck({
      messageId: 'msg-001',
      tools: ['search_tool', 'calculator'],
    });

    const ack = useTtftDecouplingStore.getState().activeAcks[ackId];
    expect(ack).toBeDefined();
    expect(ack?.messageId).toBe('msg-001');
    expect(ack?.status).toBe('intent_analyzed');
    expect(ack?.speculativeTools).toEqual(['search_tool', 'calculator']);
    expect(ack?.elapsedMs).toBe(140);
  });

  it('updates ack status and dismisses ack properly', () => {
    const store = useTtftDecouplingStore.getState();
    const ackId = store.emitEarlyAck({ messageId: 'msg-002' });

    store.updateAckStatus(ackId, 'streaming_started');
    let ack = useTtftDecouplingStore.getState().activeAcks[ackId];
    expect(ack?.status).toBe('streaming_started');

    store.dismissAck(ackId);
    ack = useTtftDecouplingStore.getState().activeAcks[ackId];
    expect(ack).toBeUndefined();
  });

  it('initializes dag timeline and updates step statuses', () => {
    const store = useTtftDecouplingStore.getState();
    store.initDagTimeline({
      dagId: 'dag-001',
      messageId: 'msg-003',
      steps: [
        { id: 's1', name: '意图拆解', isCriticalPath: true },
        { id: 's2', name: '数据并发获取', parallelGroupId: 'p1' },
      ],
    });

    let dag = useTtftDecouplingStore.getState().activeDags['dag-001'];
    expect(dag).toBeDefined();
    expect(dag?.totalSteps).toBe(2);
    expect(dag?.completedSteps).toBe(0);
    expect(dag?.isAllCompleted).toBe(false);

    // 更新第 1 步为 completed
    store.updateDagStepStatus('dag-001', 's1', 'completed', 120);
    dag = useTtftDecouplingStore.getState().activeDags['dag-001'];
    expect(dag?.completedSteps).toBe(1);
    expect(dag?.steps[0]?.status).toBe('completed');
    expect(dag?.steps[0]?.elapsedMs).toBe(120);
    expect(dag?.isAllCompleted).toBe(false);

    // 更新第 2 步为 completed，触发 isAllCompleted
    store.updateDagStepStatus('dag-001', 's2', 'completed', 240);
    dag = useTtftDecouplingStore.getState().activeDags['dag-001'];
    expect(dag?.completedSteps).toBe(2);
    expect(dag?.isAllCompleted).toBe(true);
    expect(dag?.completedAt).toBeDefined();
  });

  it('toggles timeline expansion correctly', () => {
    const store = useTtftDecouplingStore.getState();
    store.initDagTimeline({
      dagId: 'dag-002',
      messageId: 'msg-004',
      steps: [{ id: 's1', name: '步骤' }],
    });

    expect(
      useTtftDecouplingStore.getState().isTimelineExpanded['dag-002'],
    ).toBe(true);

    store.toggleTimelineExpansion('dag-002', false);
    expect(
      useTtftDecouplingStore.getState().isTimelineExpanded['dag-002'],
    ).toBe(false);

    store.toggleTimelineExpansion('dag-002');
    expect(
      useTtftDecouplingStore.getState().isTimelineExpanded['dag-002'],
    ).toBe(true);
  });
});
