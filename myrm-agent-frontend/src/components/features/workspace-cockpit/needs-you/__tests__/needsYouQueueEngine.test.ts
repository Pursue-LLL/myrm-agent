import { describe, it, expect } from 'vitest';
import {
  sortNeedsYouQueue,
  mapNeedsYouToWorkspaceTaskItems,
  deduplicateAndMergeAlerts,
  buildNeedsYouDeepLink,
  calculateQueueSummary,
} from '../needsYouQueueEngine';
import type { AnchoredAlert, NeedsYouItem } from '../needsYouTypes';

describe('needsYouQueueEngine', () => {
  const baseItem: NeedsYouItem = {
    id: 'item-1',
    source: 'approval_pending',
    title: '终端执行高危命令待批准',
    whyStopped: '安全门禁拦截',
    whatWaitingFor: '等待管理员确认授权',
    chatId: 'chat-100',
    createdAt: 10_000,
    urgency: 'normal',
    deepLinkUrl: '/chat/chat-100#needs-you?item=item-1',
  };

  describe('sortNeedsYouQueue', () => {
    it('should filter out handled or dismissed items and sort by urgency and wait time', () => {
      const items: NeedsYouItem[] = [
        { ...baseItem, id: '1', urgency: 'low', createdAt: 5_000 },
        { ...baseItem, id: '2', urgency: 'urgent', createdAt: 12_000 },
        { ...baseItem, id: '3', urgency: 'urgent', createdAt: 8_000 }, // 比 2 更早，等待更长
        { ...baseItem, id: '4', urgency: 'normal', createdAt: 9_000 },
        { ...baseItem, id: '5', urgency: 'urgent', isHandled: true },
        { ...baseItem, id: '6', urgency: 'urgent', isDismissed: true },
      ];

      const sorted = sortNeedsYouQueue(items, 20_000);
      expect(sorted.map((i) => i.id)).toEqual(['3', '2', '4', '1']);
    });
  });

  describe('mapNeedsYouToWorkspaceTaskItems', () => {
    it('should convert NeedsYouItems into standard WorkspaceTaskItems', () => {
      const items: NeedsYouItem[] = [
        {
          ...baseItem,
          id: 'task-1',
          agentId: 'agent-coder',
          agentName: 'CodePilot',
        },
      ];

      const mapped = mapNeedsYouToWorkspaceTaskItems(items, 15_000);
      expect(mapped.length).toBe(1);
      expect(mapped[0]).toEqual({
        id: 'task-1',
        title: '终端执行高危命令待批准',
        swimlane: 'needs-you',
        status: 'waiting_approval',
        chatId: 'chat-100',
        agentId: 'agent-coder',
        agentName: 'CodePilot',
        updatedAt: 10_000,
        waitingDurationMs: 5_000,
        latestOutputTail: '等待管理员确认授权',
        errorReason: '安全门禁拦截',
      });
    });
  });

  describe('deduplicateAndMergeAlerts', () => {
    it('should merge alerts within merge window for same source', () => {
      const alerts: AnchoredAlert[] = [
        {
          id: 'a1',
          itemId: 'i1',
          source: 'budget_threshold',
          title: '算力限额告警',
          summary: '已耗费 80%',
          timestamp: 10_000,
          hasShownSystemNotification: false,
          isRead: true,
          deepLinkUrl: '/chat/1',
        },
        {
          id: 'a2',
          itemId: 'i2',
          source: 'budget_threshold',
          title: '算力限额告警',
          summary: '已耗费 95%',
          timestamp: 12_000, // 相差 2000ms，在 10 分钟窗口内
          hasShownSystemNotification: false,
          isRead: false,
          deepLinkUrl: '/chat/1',
        },
        {
          id: 'a3',
          itemId: 'i3',
          source: 'approval_pending', // 不同来源
          title: '审批待处理',
          summary: '需要审批',
          timestamp: 13_000,
          hasShownSystemNotification: false,
          isRead: false,
          deepLinkUrl: '/chat/2',
        },
      ];

      const merged = deduplicateAndMergeAlerts(alerts, 60_000);
      expect(merged.length).toBe(2);
      expect(merged[0].summary).toBe('已耗费 80%; 已耗费 95%');
      expect(merged[0].isRead).toBe(false); // 有未读则合并后仍为未读
      expect(merged[1].source).toBe('approval_pending');
    });
  });

  describe('buildNeedsYouDeepLink', () => {
    it('should build proper deep link with query params and anchor', () => {
      expect(buildNeedsYouDeepLink('c123')).toBe('/chat/c123');
      expect(buildNeedsYouDeepLink('c123', 'm456')).toBe('/chat/c123?msg=m456');
      expect(buildNeedsYouDeepLink('c123', 'm456', 2, 'item-789')).toBe(
        '/chat/c123?msg=m456&turn=2#needs-you?item=item-789',
      );
    });
  });

  describe('calculateQueueSummary', () => {
    it('should calculate active counts and unread alerts correctly', () => {
      const items: NeedsYouItem[] = [
        { ...baseItem, id: '1', urgency: 'urgent', createdAt: 5_000 },
        { ...baseItem, id: '2', urgency: 'normal', createdAt: 12_000 },
        { ...baseItem, id: '3', isHandled: true },
      ];
      const alerts: AnchoredAlert[] = [
        {
          id: 'a1',
          itemId: '1',
          source: 'approval_pending',
          title: 't1',
          summary: 's1',
          timestamp: 10_000,
          hasShownSystemNotification: false,
          isRead: false,
          deepLinkUrl: '',
        },
        {
          id: 'a2',
          itemId: '2',
          source: 'approval_pending',
          title: 't2',
          summary: 's2',
          timestamp: 10_000,
          hasShownSystemNotification: false,
          isRead: true,
          deepLinkUrl: '',
        },
      ];

      const summary = calculateQueueSummary(items, alerts, 20_000);
      expect(summary.totalPendingCount).toBe(2);
      expect(summary.urgentCount).toBe(1);
      expect(summary.normalCount).toBe(1);
      expect(summary.longestWaitingMs).toBe(15_000); // 20000 - 5000
      expect(summary.unreadAlertCount).toBe(1);
    });
  });
});
