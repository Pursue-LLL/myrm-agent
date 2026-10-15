import { describe, it, expect, beforeEach } from 'vitest';
import { useSideChatStore } from '../useSideChatStore';

describe('useSideChatStore', () => {
  beforeEach(() => {
    useSideChatStore.getState().reset();
  });

  it('初始状态合规', () => {
    const state = useSideChatStore.getState();
    expect(state.isOpen).toBe(false);
    expect(state.isDocked).toBe(false);
    expect(state.messages).toEqual([]);
    expect(state.steeringQueue).toEqual([]);
    expect(state.unreadCount).toBe(0);
    expect(state.mainTask.status).toBe('running');
  });

  it('支持切换展开状态、停靠模式以及未读计数归零', () => {
    const store = useSideChatStore.getState();
    store.sendSideMessage('顺手加个功能'); // 抽屉关闭时发，增加未读
    expect(useSideChatStore.getState().unreadCount).toBe(1);

    store.setOpen(true);
    expect(useSideChatStore.getState().isOpen).toBe(true);
    expect(useSideChatStore.getState().unreadCount).toBe(0);

    store.setDocked(true);
    expect(useSideChatStore.getState().isDocked).toBe(true);
  });

  it('发送状态问答时，自动触发协作者秒回且不压入排队队列', () => {
    const store = useSideChatStore.getState();
    store.sendSideMessage('当前执行到哪一步了？');

    const state = useSideChatStore.getState();
    expect(state.messages.length).toBe(2); // user + assistant
    expect(state.messages[0]?.role).toBe('user');
    expect(state.messages[0]?.steeringStatus).toBe('instant_answered');
    expect(state.messages[1]?.role).toBe('assistant');
    expect(state.messages[1]?.content).toContain('[协作者即时同步]');
    expect(state.steeringQueue.length).toBe(0); // 问答不占用主任务微调队列
  });

  it('发送增量需求时，自动压入微调队列并标记为 pending_injection', () => {
    const store = useSideChatStore.getState();
    store.sendSideMessage('顺便增加导出 CSV 功能');

    const state = useSideChatStore.getState();
    expect(state.messages[0]?.steeringStatus).toBe('pending_injection');
    expect(state.steeringQueue.length).toBe(1);
    expect(state.steeringQueue[0]?.intentType).toBe('incremental_feature');
    expect(state.steeringQueue[0]?.status).toBe('pending');
  });

  it('模拟主任务步进消费微调队列 (consumeSteeringInNextStep)', () => {
    const store = useSideChatStore.getState();
    store.sendSideMessage('增加导出功能');
    expect(useSideChatStore.getState().steeringQueue[0]?.status).toBe('pending');

    const consumed = store.consumeSteeringInNextStep(3);
    expect(consumed.length).toBe(1);

    const state = useSideChatStore.getState();
    expect(state.steeringQueue[0]?.status).toBe('consumed');
    expect(state.steeringQueue[0]?.consumedAtStep).toBe(3);
    expect(state.messages[0]?.steeringStatus).toBe('injected_to_main');
    expect(state.messages[0]?.injectedAtStep).toBe(3);
    // 应有系统广播
    expect(state.messages.some((m) => m.role === 'system')).toBe(true);
  });

  it('支持撤回微调条目', () => {
    const store = useSideChatStore.getState();
    store.sendSideMessage('加个无用字段');
    const itemId = useSideChatStore.getState().steeringQueue[0]?.id;
    expect(itemId).toBeDefined();

    if (itemId) {
      store.dismissSteeringItem(itemId);
      const state = useSideChatStore.getState();
      expect(state.steeringQueue[0]?.status).toBe('cancelled');
      expect(state.messages[0]?.steeringStatus).toBe('discarded');
    }
  });
});
