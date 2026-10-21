import { describe, it, expect } from 'vitest';
import type {
  FeedSourceSystem,
  FeedItemStatus,
  FeedAutonomyTier,
  FeedPriority,
  ActivityFeedItem,
  ActivityFeedFilter,
  SourceSystemMeta,
  ActivityFeedStoreState,
} from '../activityFeedTypes';

describe('activityFeedTypes', () => {
  it('correctly models ActivityFeedItem contract', () => {
    const item: ActivityFeedItem = {
      id: 'feed_101',
      sourceSystem: 'email',
      sourceRefId: 'em_8848',
      title: '客户合作协议草案',
      summary: '收到法务邮件，已自动完成初审',
      autonomyTier: 'full_autonomous',
      status: 'evaporating',
      timestamp: 1760000000000,
      resolvedAt: 1760000001000,
      evaporationTtlMs: 5000,
      priority: 'high',
      payloadSnippet: 'NDA terms agreement attached',
    };

    expect(item.id).toBe('feed_101');
    expect(item.sourceSystem).toBe<FeedSourceSystem>('email');
    expect(item.status).toBe<FeedItemStatus>('evaporating');
    expect(item.autonomyTier).toBe<FeedAutonomyTier>('full_autonomous');
    expect(item.priority).toBe<FeedPriority>('high');
  });

  it('correctly models ActivityFeedFilter contract', () => {
    const filter: ActivityFeedFilter = {
      sourceSystem: 'approval',
      status: 'pending_decision',
      onlyHumanRequired: true,
      searchQuery: '合同',
    };

    expect(filter.sourceSystem).toBe('approval');
    expect(filter.onlyHumanRequired).toBe(true);
    expect(filter.searchQuery).toBe('合同');
  });

  it('correctly models SourceSystemMeta contract', () => {
    const meta: SourceSystemMeta = {
      source: 'calendar',
      label: '日程日历',
      badgeColor: 'sky',
    };

    expect(meta.source).toBe('calendar');
    expect(meta.badgeColor).toBe('sky');
  });

  it('correctly models ActivityFeedStoreState contract', () => {
    const state: ActivityFeedStoreState = {
      items: [],
      archive: [],
      filter: {
        sourceSystem: 'all',
        status: 'all',
        onlyHumanRequired: false,
        searchQuery: '',
      },
      isEvaporationPaused: false,
    };

    expect(state.items).toEqual([]);
    expect(state.archive).toEqual([]);
    expect(state.isEvaporationPaused).toBe(false);
  });
});
