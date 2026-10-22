import {
  ChannelFootprintItem,
  ChannelType,
  FootprintCategory,
} from './weeklyDigestTypes';

export const INITIAL_CHANNEL_FOOTPRINTS: ChannelFootprintItem[] = [
  {
    id: 'fp-feishu-pr-402',
    channel: 'feishu',
    category: 'pr-review',
    title: 'PR #402 交易网关零拷贝通道 Review',
    description: '在飞书群协同完成对 Rust 网关内存映射零拷贝优化的评审，排查出 1 处死锁边界并提出安全降级方案。',
    metrics: '通过 18 项集成用例，延迟降低 35%',
    artifactRef: 'https://github.com/myrm/gateway/pull/402',
    timestamp: Date.now() - 4 * 24 * 3600 * 1000,
    includedInDigest: true,
  },
  {
    id: 'fp-desktop-build-09',
    channel: 'desktop',
    category: 'deliverable',
    title: 'Tauri 桌面端 PTY 真实多终端会话池交付',
    description: '在 macOS/Windows 双端打通 ANSI 彩色流式传输，完成独立侧栏终端 Tab 闭环与单元测试。',
    metrics: '单测 100% 全绿，文件受控在 280 行内',
    artifactRef: 'src/components/features/workbench/WorkbenchTerminal.tsx',
    timestamp: Date.now() - 3 * 24 * 3600 * 1000,
    includedInDigest: true,
  },
  {
    id: 'fp-web-rfc-cache',
    channel: 'web',
    category: 'rfc-decision',
    title: 'RFC-2026-08: 多租户向量检索分级缓存决策',
    description: '在 WebUI 架构讨论室与跨团队对齐分级缓存策略，确定采用双层 LRU + Redis 分布式兜底。',
    metrics: '节省 40% 远程检索开销，对齐 4 位技术委员会成员',
    artifactRef: 'docs/rfcs/2026-08-vector-cache.md',
    timestamp: Date.now() - 2 * 24 * 3600 * 1000,
    includedInDigest: true,
  },
  {
    id: 'fp-cli-bench-profile',
    channel: 'cli',
    category: 'learning',
    title: 'CLI 长上下文吞吐性能压测与 GC 踩坑沉淀',
    description: '在命令行持续压测 1M Token 处理性能，定位到 V8 老生代内存回收抖动问题并制定定时分块回收规则。',
    metrics: 'GC 暂停时间从 420ms 降至 65ms',
    artifactRef: 'benchmarks/results/1m-context-profile.json',
    timestamp: Date.now() - 1 * 24 * 3600 * 1000,
    includedInDigest: true,
  },
  {
    id: 'fp-wechat-risk-alert',
    channel: 'wechat',
    category: 'risk-roadblock',
    title: '微信移动端 Webhook 频控预警与未决风险',
    description: '在微信服务号收到第三方上游服务商关于高频推送频率限制的邮件通告，下周需补齐漏桶队列。',
    metrics: '峰值达到 85 QPS 接近 100 QPS 阈值',
    artifactRef: 'ticket/INC-8891',
    timestamp: Date.now() - 8 * 3600 * 1000,
    includedInDigest: true,
  },
];

export function getChannelDisplayName(channel: ChannelType): string {
  switch (channel) {
    case 'feishu':
      return '飞书协同';
    case 'wechat':
      return '微信生态';
    case 'desktop':
      return '桌面客户端';
    case 'web':
      return 'Web 控制台';
    case 'cli':
      return '终端 CLI';
    default:
      return '通用渠道';
  }
}

export function getCategoryDisplayName(category: FootprintCategory): string {
  switch (category) {
    case 'pr-review':
      return '代码评审 (PR)';
    case 'rfc-decision':
      return '架构决策 (RFC)';
    case 'deliverable':
      return '核心成果交付';
    case 'learning':
      return '技术沉淀与经验';
    case 'risk-roadblock':
      return '卡点风险与阻塞';
    default:
      return '其他事项';
  }
}

export function filterFootprintsByChannel(
  items: ChannelFootprintItem[],
  channel: ChannelType | 'all'
): ChannelFootprintItem[] {
  if (channel === 'all') {
    return items;
  }
  return items.filter((item) => item.channel === channel);
}

export function filterFootprintsByCategory(
  items: ChannelFootprintItem[],
  category: FootprintCategory | 'all'
): ChannelFootprintItem[] {
  if (category === 'all') {
    return items;
  }
  return items.filter((item) => item.category === category);
}

export interface FootprintStats {
  totalCount: number;
  includedCount: number;
  channelCounts: Record<ChannelType, number>;
  categoryCounts: Record<FootprintCategory, number>;
}

export function computeFootprintStats(items: ChannelFootprintItem[]): FootprintStats {
  const channelCounts: Record<ChannelType, number> = {
    feishu: 0,
    wechat: 0,
    desktop: 0,
    web: 0,
    cli: 0,
  };

  const categoryCounts: Record<FootprintCategory, number> = {
    'pr-review': 0,
    'rfc-decision': 0,
    deliverable: 0,
    learning: 0,
    'risk-roadblock': 0,
  };

  let includedCount = 0;

  for (const item of items) {
    if (channelCounts[item.channel] !== undefined) {
      channelCounts[item.channel] += 1;
    }
    if (categoryCounts[item.category] !== undefined) {
      categoryCounts[item.category] += 1;
    }
    if (item.includedInDigest) {
      includedCount += 1;
    }
  }

  return {
    totalCount: items.length,
    includedCount,
    channelCounts,
    categoryCounts,
  };
}
