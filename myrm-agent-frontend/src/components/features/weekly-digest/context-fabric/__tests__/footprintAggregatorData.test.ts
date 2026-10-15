import { describe, it, expect } from 'vitest';
import {
  computeFootprintStats,
  filterFootprintsByChannel,
  filterFootprintsByCategory,
  getCategoryDisplayName,
  getChannelDisplayName,
  INITIAL_CHANNEL_FOOTPRINTS,
} from '../footprintAggregatorData';
import { ChannelFootprintItem } from '../weeklyDigestTypes';

describe('footprintAggregatorData pure functions', () => {
  it('returns human-readable display names for channels and categories', () => {
    expect(getChannelDisplayName('feishu')).toBe('飞书协同');
    expect(getChannelDisplayName('wechat')).toBe('微信生态');
    expect(getChannelDisplayName('desktop')).toBe('桌面客户端');
    expect(getChannelDisplayName('web')).toBe('Web 控制台');
    expect(getChannelDisplayName('cli')).toBe('终端 CLI');

    expect(getCategoryDisplayName('pr-review')).toBe('代码评审 (PR)');
    expect(getCategoryDisplayName('rfc-decision')).toBe('架构决策 (RFC)');
    expect(getCategoryDisplayName('deliverable')).toBe('核心成果交付');
    expect(getCategoryDisplayName('learning')).toBe('技术沉淀与经验');
    expect(getCategoryDisplayName('risk-roadblock')).toBe('卡点风险与阻塞');
  });

  it('filters footprints by channel accurately', () => {
    const all = filterFootprintsByChannel(INITIAL_CHANNEL_FOOTPRINTS, 'all');
    expect(all.length).toBe(INITIAL_CHANNEL_FOOTPRINTS.length);

    const feishuOnly = filterFootprintsByChannel(INITIAL_CHANNEL_FOOTPRINTS, 'feishu');
    expect(feishuOnly.every((item) => item.channel === 'feishu')).toBe(true);
    expect(feishuOnly.length).toBeGreaterThan(0);

    const desktopOnly = filterFootprintsByChannel(INITIAL_CHANNEL_FOOTPRINTS, 'desktop');
    expect(desktopOnly.every((item) => item.channel === 'desktop')).toBe(true);
  });

  it('filters footprints by category accurately', () => {
    const all = filterFootprintsByCategory(INITIAL_CHANNEL_FOOTPRINTS, 'all');
    expect(all.length).toBe(INITIAL_CHANNEL_FOOTPRINTS.length);

    const deliverables = filterFootprintsByCategory(
      INITIAL_CHANNEL_FOOTPRINTS,
      'deliverable'
    );
    expect(deliverables.every((item) => item.category === 'deliverable')).toBe(true);

    const rfcs = filterFootprintsByCategory(
      INITIAL_CHANNEL_FOOTPRINTS,
      'rfc-decision'
    );
    expect(rfcs.every((item) => item.category === 'rfc-decision')).toBe(true);
  });

  it('computes footprint statistics correctly', () => {
    const stats = computeFootprintStats(INITIAL_CHANNEL_FOOTPRINTS);

    expect(stats.totalCount).toBe(INITIAL_CHANNEL_FOOTPRINTS.length);
    expect(stats.includedCount).toBe(INITIAL_CHANNEL_FOOTPRINTS.length);
    expect(stats.channelCounts.feishu).toBe(1);
    expect(stats.channelCounts.desktop).toBe(1);
    expect(stats.categoryCounts['pr-review']).toBe(1);
    expect(stats.categoryCounts['rfc-decision']).toBe(1);

    const itemsWithExclusions: ChannelFootprintItem[] = [
      ...INITIAL_CHANNEL_FOOTPRINTS,
      {
        id: 'fp-test-excluded',
        channel: 'cli',
        category: 'learning',
        title: '测试排除项',
        description: '仅用于统计测试',
        timestamp: Date.now(),
        includedInDigest: false,
      },
    ];

    const stats2 = computeFootprintStats(itemsWithExclusions);
    expect(stats2.totalCount).toBe(INITIAL_CHANNEL_FOOTPRINTS.length + 1);
    expect(stats2.includedCount).toBe(INITIAL_CHANNEL_FOOTPRINTS.length);
  });
});
