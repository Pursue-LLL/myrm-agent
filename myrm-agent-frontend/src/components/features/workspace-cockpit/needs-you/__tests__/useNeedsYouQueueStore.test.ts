import { describe, it, expect, beforeEach } from 'vitest';
import { useNeedsYouQueueStore } from '../useNeedsYouQueueStore';

describe('useNeedsYouQueueStore', () => {
  beforeEach(() => {
    useNeedsYouQueueStore.getState().reset();
  });

  it('should register interruption with dual-write into items and alerts', () => {
    const id = useNeedsYouQueueStore.getState().registerInterruption({
      source: 'approval_pending',
      title: '高危命令确认',
      whyStopped: '安全规则要求人工授权',
      whatWaitingFor: '等待管理员审批',
      chatId: 'chat-42',
      urgency: 'urgent',
    });

    const state = useNeedsYouQueueStore.getState();
    expect(state.items.length).toBe(1);
    expect(state.items[0].id).toBe(id);
    expect(state.items[0].isHandled).toBe(false);
    expect(state.items[0].isDismissed).toBe(false);

    // 验证双写生成的后台告警
    expect(state.alerts.length).toBe(1);
    expect(state.alerts[0].itemId).toBe(id);
    expect(state.alerts[0].isRead).toBe(false);
  });

  it('should resolve interruption and mark it handled', () => {
    const id = useNeedsYouQueueStore.getState().registerInterruption({
      source: 'goal_needs_review',
      title: '拆解目标待确认',
      whyStopped: '关键里程碑需确认',
      whatWaitingFor: '用户评审',
      chatId: 'chat-42',
      urgency: 'normal',
    });

    useNeedsYouQueueStore.getState().resolveInterruption(id);
    const item = useNeedsYouQueueStore.getState().items.find((i) => i.id === id);
    expect(item?.isHandled).toBe(true);
  });

  it('should dismiss interruption with reason to prevent silent drop', () => {
    const id = useNeedsYouQueueStore.getState().registerInterruption({
      source: 'kanban_human_block',
      title: '泳道卡片阻塞',
      whyStopped: '缺少外部 API 密钥',
      whatWaitingFor: '配置密钥',
      chatId: 'chat-42',
      urgency: 'low',
    });

    useNeedsYouQueueStore.getState().openReasonModal(id);
    expect(useNeedsYouQueueStore.getState().isReasonModalOpen).toBe(true);

    useNeedsYouQueueStore.getState().dismissInterruption(id, '已改由其他渠道离线配置');
    const state = useNeedsYouQueueStore.getState();
    const item = state.items.find((i) => i.id === id);

    expect(item?.isDismissed).toBe(true);
    expect(item?.dismissReason).toBe('已改由其他渠道离线配置');
    expect(state.isReasonModalOpen).toBe(false);
    expect(state.dismissTargetId).toBeNull();
  });

  it('should batch resolve selected items', () => {
    const id1 = useNeedsYouQueueStore.getState().registerInterruption({
      source: 'task_failed_retry',
      title: '任务失败 1',
      whyStopped: '超时',
      whatWaitingFor: '重试授权',
      chatId: 'c1',
      urgency: 'normal',
    });
    const id2 = useNeedsYouQueueStore.getState().registerInterruption({
      source: 'task_failed_retry',
      title: '任务失败 2',
      whyStopped: '超时',
      whatWaitingFor: '重试授权',
      chatId: 'c2',
      urgency: 'normal',
    });

    useNeedsYouQueueStore.getState().selectAll();
    expect(useNeedsYouQueueStore.getState().selectedItemIds).toEqual([id2, id1]);

    useNeedsYouQueueStore.getState().batchResolve([id1, id2]);
    const items = useNeedsYouQueueStore.getState().items;
    expect(items.every((i) => i.isHandled)).toBe(true);
    expect(useNeedsYouQueueStore.getState().selectedItemIds).toEqual([]);
  });

  it('should manage drawer opening and focus tracking', () => {
    useNeedsYouQueueStore.getState().openDrawer('item-999');
    expect(useNeedsYouQueueStore.getState().isDrawerOpen).toBe(true);
    expect(useNeedsYouQueueStore.getState().focusedItemId).toBe('item-999');

    useNeedsYouQueueStore.getState().closeDrawer();
    expect(useNeedsYouQueueStore.getState().isDrawerOpen).toBe(false);
    expect(useNeedsYouQueueStore.getState().focusedItemId).toBeNull();
  });

  it('should toggle read status of anchored alerts', () => {
    useNeedsYouQueueStore.getState().registerInterruption({
      source: 'budget_threshold',
      title: '额度预警',
      whyStopped: '预算超限',
      whatWaitingFor: '调优限额',
      chatId: 'c1',
      urgency: 'urgent',
    });

    const alertId = useNeedsYouQueueStore.getState().alerts[0].id;
    useNeedsYouQueueStore.getState().markAlertRead(alertId);
    expect(useNeedsYouQueueStore.getState().alerts[0].isRead).toBe(true);
  });
});
