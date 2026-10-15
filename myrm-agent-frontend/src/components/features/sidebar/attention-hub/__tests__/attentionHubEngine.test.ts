import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { AttentionItem, AttentionFilterState } from '../attentionHubTypes';
import {
  computePriorityWeight,
  sortAttentionItems,
  getCategoryMeta,
  formatRemainingTime,
  filterAttentionItems,
  generateAnchorElementId,
  performSmoothShuttle,
} from '../attentionHubEngine';

describe('attentionHubEngine', () => {
  describe('computePriorityWeight', () => {
    it('returns correct numeric weights for priorities', () => {
      expect(computePriorityWeight('urgent')).toBe(4);
      expect(computePriorityWeight('high')).toBe(3);
      expect(computePriorityWeight('medium')).toBe(2);
      expect(computePriorityWeight('info')).toBe(1);
    });
  });

  describe('sortAttentionItems', () => {
    it('sorts actionRequired items before info items, then by priority, then by timestamp', () => {
      const items: AttentionItem[] = [
        {
          id: '1',
          chatId: 'c1',
          chatTitle: 'Chat 1',
          category: 'task_completed',
          priority: 'urgent',
          title: '已完成但标记为urgent',
          description: '',
          timestamp: 1000,
          isRead: false,
          actionRequired: false,
        },
        {
          id: '2',
          chatId: 'c2',
          chatTitle: 'Chat 2',
          category: 'approval_blocking',
          priority: 'medium',
          title: '中等审批',
          description: '',
          timestamp: 2000,
          isRead: false,
          actionRequired: true,
        },
        {
          id: '3',
          chatId: 'c3',
          chatTitle: 'Chat 3',
          category: 'approval_blocking',
          priority: 'urgent',
          title: '紧急审批',
          description: '',
          timestamp: 1500,
          isRead: false,
          actionRequired: true,
        },
      ];

      const sorted = sortAttentionItems(items);
      // Item 3 (actionRequired=true, urgent) comes first
      expect(sorted[0].id).toBe('3');
      // Item 2 (actionRequired=true, medium) comes second
      expect(sorted[1].id).toBe('2');
      // Item 1 (actionRequired=false) comes last
      expect(sorted[2].id).toBe('1');
    });
  });

  describe('getCategoryMeta', () => {
    it('returns metadata for each category', () => {
      expect(getCategoryMeta('approval_blocking').label).toBe('待审批');
      expect(getCategoryMeta('approval_blocking').badgeColor).toBe('rose');

      expect(getCategoryMeta('clarification_needed').label).toBe('待答复');
      expect(getCategoryMeta('clarification_needed').badgeColor).toBe('amber');

      expect(getCategoryMeta('task_failed').label).toBe('任务异常');
      expect(getCategoryMeta('task_failed').badgeColor).toBe('orange');

      expect(getCategoryMeta('task_completed').label).toBe('任务已完成');
      expect(getCategoryMeta('task_completed').badgeColor).toBe('emerald');
    });
  });

  describe('formatRemainingTime', () => {
    const baseNow = 1760000000000;

    it('returns null if no expiresAt is provided', () => {
      expect(formatRemainingTime(undefined, baseNow)).toBeNull();
    });

    it('returns "已超时" if expired', () => {
      expect(formatRemainingTime(baseNow - 1000, baseNow)).toBe('已超时');
    });

    it('formats seconds if under 1 minute', () => {
      expect(formatRemainingTime(baseNow + 30000, baseNow)).toBe('30秒后超时');
    });

    it('formats minutes if under 1 hour', () => {
      expect(formatRemainingTime(baseNow + 120000, baseNow)).toBe('2分后超时');
    });

    it('formats hours if >= 1 hour', () => {
      expect(formatRemainingTime(baseNow + 7200000, baseNow)).toBe('2小时后超时');
    });
  });

  describe('filterAttentionItems', () => {
    const items: AttentionItem[] = [
      {
        id: '1',
        chatId: 'c1',
        chatTitle: '代码重构项目',
        category: 'approval_blocking',
        priority: 'urgent',
        title: '删除旧组件审批',
        description: '需要确认删除废弃代码',
        timestamp: 1000,
        isRead: false,
        actionRequired: true,
      },
      {
        id: '2',
        chatId: 'c2',
        chatTitle: '数据报表生成',
        category: 'task_completed',
        priority: 'info',
        title: '报表已导出',
        description: '文件存放在 exports 目录',
        timestamp: 2000,
        isRead: true,
        actionRequired: false,
      },
    ];

    it('filters by category', () => {
      const filter: AttentionFilterState = {
        category: 'approval_blocking',
        onlyActionRequired: false,
        searchQuery: '',
      };
      const result = filterAttentionItems(items, filter);
      expect(result.length).toBe(1);
      expect(result[0].id).toBe('1');
    });

    it('filters by onlyActionRequired', () => {
      const filter: AttentionFilterState = {
        category: 'all',
        onlyActionRequired: true,
        searchQuery: '',
      };
      const result = filterAttentionItems(items, filter);
      expect(result.length).toBe(1);
      expect(result[0].id).toBe('1');
    });

    it('filters by searchQuery matching title or chatTitle', () => {
      const filter: AttentionFilterState = {
        category: 'all',
        onlyActionRequired: false,
        searchQuery: '报表',
      };
      const result = filterAttentionItems(items, filter);
      expect(result.length).toBe(1);
      expect(result[0].id).toBe('2');
    });
  });

  describe('generateAnchorElementId', () => {
    it('uses anchorNodeId when provided', () => {
      expect(generateAnchorElementId('chat_1', 'msg_42')).toBe('msg_42');
    });

    it('falls back to session anchor ID when anchorNodeId is absent', () => {
      expect(generateAnchorElementId('chat_1', undefined)).toBe('chat-session-chat_1');
    });
  });

  describe('performSmoothShuttle', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('returns false when target element does not exist', () => {
      expect(performSmoothShuttle('non_existent_node')).toBe(false);
    });

    it('scrolls and adds temporary highlight ring when target element exists', () => {
      const el = document.createElement('div');
      el.id = 'target_anchor_1';
      const scrollIntoViewMock = vi.fn();
      Object.defineProperty(el, 'scrollIntoView', {
        value: scrollIntoViewMock,
        writable: true,
        configurable: true,
      });
      document.body.appendChild(el);

      const success = performSmoothShuttle('target_anchor_1');
      expect(success).toBe(true);
      expect(scrollIntoViewMock).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' });
      expect(el.classList.contains('ring-rose-500')).toBe(true);

      vi.advanceTimersByTime(2100);
      expect(el.classList.contains('ring-rose-500')).toBe(false);

      document.body.removeChild(el);
    });
  });
});
