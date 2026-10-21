import { describe, it, expect } from 'vitest';
import type { ActivityFeedItem, ActivityFeedFilter } from '../activityFeedTypes';
import {
  classifyAutonomyTier,
  computePriorityWeight,
  sortActivityFeed,
  computeEvaporationProgress,
  getSourceSystemMeta,
  filterActivityFeed,
} from '../activityFeedEngine';

describe('activityFeedEngine', () => {
  describe('classifyAutonomyTier', () => {
    it('classifies high-risk or explicit approval as human_decision_required', () => {
      expect(classifyAutonomyTier('approval', 0.2, false)).toBe('human_decision_required');
      expect(classifyAutonomyTier('email', 0.1, true)).toBe('human_decision_required');
      expect(classifyAutonomyTier('cron', 0.85, false)).toBe('human_decision_required');
    });

    it('classifies medium risk as supervised', () => {
      expect(classifyAutonomyTier('messaging', 0.5, false)).toBe('supervised');
    });

    it('classifies low risk as full_autonomous', () => {
      expect(classifyAutonomyTier('calendar', 0.1, false)).toBe('full_autonomous');
    });
  });

  describe('computePriorityWeight', () => {
    it('calculates numerical priority weights correctly', () => {
      expect(computePriorityWeight('urgent')).toBe(4);
      expect(computePriorityWeight('high')).toBe(3);
      expect(computePriorityWeight('normal')).toBe(2);
      expect(computePriorityWeight('low')).toBe(1);
    });
  });

  describe('sortActivityFeed', () => {
    it('pins human_decision_required items to top, followed by priority and timestamp', () => {
      const items: ActivityFeedItem[] = [
        {
          id: '1',
          sourceSystem: 'cron',
          sourceRefId: 'c1',
          title: '定时抓取',
          summary: '常规',
          autonomyTier: 'full_autonomous',
          status: 'pending_decision',
          timestamp: 3000,
          priority: 'urgent',
        },
        {
          id: '2',
          sourceSystem: 'approval',
          sourceRefId: 'a1',
          title: '合同签署',
          summary: '需要法务审批',
          autonomyTier: 'human_decision_required',
          status: 'pending_decision',
          timestamp: 1000,
          priority: 'normal',
        },
        {
          id: '3',
          sourceSystem: 'email',
          sourceRefId: 'e1',
          title: '邮件归档',
          summary: '自动归档',
          autonomyTier: 'full_autonomous',
          status: 'evaporating',
          timestamp: 2000,
          priority: 'normal',
        },
      ];

      const sorted = sortActivityFeed(items);
      // Item 2 is human_decision_required -> index 0
      expect(sorted[0].id).toBe('2');
      // Item 1 is active (not evaporating) with urgent priority -> index 1
      expect(sorted[1].id).toBe('1');
      // Item 3 is evaporating -> index 2
      expect(sorted[2].id).toBe('3');
    });
  });

  describe('computeEvaporationProgress', () => {
    const baseNow = 1760000000000;

    it('returns 0 when resolvedAt is missing or in the future', () => {
      expect(computeEvaporationProgress(undefined, 5000, baseNow)).toBe(0);
      expect(computeEvaporationProgress(baseNow + 1000, 5000, baseNow)).toBe(0);
    });

    it('returns 1 when elapsed exceeds ttlMs', () => {
      expect(computeEvaporationProgress(baseNow - 6000, 5000, baseNow)).toBe(1);
    });

    it('returns proportional progress within duration', () => {
      const p = computeEvaporationProgress(baseNow - 2500, 5000, baseNow);
      expect(p).toBe(0.5);
    });
  });

  describe('getSourceSystemMeta', () => {
    it('returns metadata for all 6 systems', () => {
      expect(getSourceSystemMeta('email').label).toBe('邮件服务');
      expect(getSourceSystemMeta('calendar').label).toBe('日程日历');
      expect(getSourceSystemMeta('messaging').label).toBe('即时消息');
      expect(getSourceSystemMeta('approval').label).toBe('审批决断');
      expect(getSourceSystemMeta('cron').label).toBe('定时调度');
      expect(getSourceSystemMeta('kanban').label).toBe('看板任务');
    });
  });

  describe('filterActivityFeed', () => {
    const items: ActivityFeedItem[] = [
      {
        id: '1',
        sourceSystem: 'email',
        sourceRefId: 'ref_101',
        title: '新发票通知',
        summary: '阿里云月度发票到达',
        autonomyTier: 'full_autonomous',
        status: 'pending_decision',
        timestamp: 1000,
        priority: 'normal',
      },
      {
        id: '2',
        sourceSystem: 'approval',
        sourceRefId: 'ref_202',
        title: '生产部署申请',
        summary: '前端 v2.4 灰度发布',
        autonomyTier: 'human_decision_required',
        status: 'pending_decision',
        timestamp: 2000,
        priority: 'urgent',
      },
    ];

    it('filters by sourceSystem', () => {
      const filter: ActivityFeedFilter = {
        sourceSystem: 'approval',
        status: 'all',
        onlyHumanRequired: false,
        searchQuery: '',
      };
      const res = filterActivityFeed(items, filter);
      expect(res.length).toBe(1);
      expect(res[0].id).toBe('2');
    });

    it('filters by onlyHumanRequired', () => {
      const filter: ActivityFeedFilter = {
        sourceSystem: 'all',
        status: 'all',
        onlyHumanRequired: true,
        searchQuery: '',
      };
      const res = filterActivityFeed(items, filter);
      expect(res.length).toBe(1);
      expect(res[0].id).toBe('2');
    });

    it('filters by searchQuery matching title or refId', () => {
      const filter: ActivityFeedFilter = {
        sourceSystem: 'all',
        status: 'all',
        onlyHumanRequired: false,
        searchQuery: '发票',
      };
      const res = filterActivityFeed(items, filter);
      expect(res.length).toBe(1);
      expect(res[0].id).toBe('1');
    });
  });
});
