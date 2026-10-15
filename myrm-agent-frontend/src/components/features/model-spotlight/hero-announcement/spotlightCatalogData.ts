import {
  DismissRecord,
  MountComparison,
  SpotlightModelItem,
} from './modelSpotlightTypes';

export const SPOTLIGHT_CATALOG: SpotlightModelItem[] = [
  {
    id: 'spotlight-gpt-6-astra',
    modelId: 'openai/gpt-6-astra',
    name: 'GPT-6 Astra',
    provider: 'OpenAI',
    tagline: '次世代超大规模多模态推理旗舰，支持 1M 原生超长上下文与近瞬时思维链',
    highlightBadges: ['flagship', 'reasoning', 'multimodal'],
    contextWindow: 1_000_000,
    pricingInputPerM: 2.5,
    pricingOutputPerM: 10.0,
    discountPercent: 20,
    releaseDate: '2026-09-06',
    spotlightGradient: {
      from: 'from-violet-600/30',
      to: 'to-indigo-900/40',
      accent: 'border-violet-500/50',
    },
    benchmarks: [
      { label: 'SWE-bench Verified', score: '78.4%', vsPrior: '+14.2%' },
      { label: 'AIME 2026 Math', score: '93.5%', vsPrior: '+8.1%' },
      { label: '首字延迟 (TTFT)', score: '185ms', vsPrior: '-42%' },
    ],
    samplePrompts: [
      '用 TypeScript 实现一个支持 LRU 驱逐与异步穿透防护的高性能内存缓存引擎。',
      '分析一段高并发交易网关中的分布式死锁风险并设计降级策略。',
      '重构前端状态机，消除冗余计算并生成符合无障碍规范的语义化交互组件。',
    ],
  },
  {
    id: 'spotlight-claude-3-7-sonnet',
    modelId: 'anthropic/claude-3-7-sonnet',
    name: 'Claude 3.7 Sonnet (Hybrid Thinking)',
    provider: 'Anthropic',
    tagline: '混合思考模式架构，平衡亚秒级日常对话与百万 Token 深度复杂推理',
    highlightBadges: ['reasoning', 'ultra-fast', 'flagship'],
    contextWindow: 500_000,
    pricingInputPerM: 3.0,
    pricingOutputPerM: 15.0,
    releaseDate: '2026-08-28',
    spotlightGradient: {
      from: 'from-amber-600/25',
      to: 'to-orange-900/40',
      accent: 'border-amber-500/50',
    },
    benchmarks: [
      { label: 'HumanEval Pro', score: '92.1%', vsPrior: '+9.4%' },
      { label: 'GPQA Diamond', score: '74.6%', vsPrior: '+6.8%' },
      { label: '长文本 Needle Recall', score: '99.8%', vsPrior: '+0.5%' },
    ],
    samplePrompts: [
      '审查这篇系统架构设计草案，指出 3 个隐藏的单点失效风险并提出修复方案。',
      '对比基于 WebSocket 与 Server-Sent Events 实现长任务推送的取舍。',
      '编写一个极简且类型安全的前端状态管理 Hook，支持原子订阅。',
    ],
  },
  {
    id: 'spotlight-deepseek-v3',
    modelId: 'deepseek/deepseek-chat-v3',
    name: 'DeepSeek-V3 Reasoning',
    provider: 'DeepSeek',
    tagline: '开源权重顶峰 MoE 架构，极高吞吐量与极优性价比',
    highlightBadges: ['open-weights', 'discount', 'ultra-fast'],
    contextWindow: 128_000,
    pricingInputPerM: 0.27,
    pricingOutputPerM: 1.1,
    discountPercent: 50,
    releaseDate: '2026-08-15',
    spotlightGradient: {
      from: 'from-blue-600/25',
      to: 'to-cyan-900/40',
      accent: 'border-cyan-500/50',
    },
    benchmarks: [
      { label: 'MMLU-Pro', score: '84.2%', vsPrior: '+11.0%' },
      { label: 'MATH 500', score: '90.2%', vsPrior: '+15.4%' },
      { label: '生成吞吐量', score: '95 Tok/s', vsPrior: '+60%' },
    ],
    samplePrompts: [
      '用最紧凑的 Python 代码实现 LeetCode 42 接雨水，并给出 O(1) 空间复杂度证明。',
      '解释 Linux 内核 epoll 水平触发与边缘触发的区别与踩坑点。',
      '为多租户系统设计基于 PostgreSQL 行级安全的权限隔离策略。',
    ],
  },
];

const DEFAULT_CURRENT_MODEL_SPECS: Record<string, { context: number; priceInput: number }> = {
  'openai/gpt-4o': { context: 128_000, priceInput: 5.0 },
  'anthropic/claude-3-5-sonnet': { context: 200_000, priceInput: 3.0 },
  'deepseek/deepseek-chat': { context: 64_000, priceInput: 0.5 },
  default: { context: 128_000, priceInput: 3.0 },
};

export function formatTokenCount(tokens: number): string {
  if (tokens >= 1_000_000) {
    const millions = tokens / 1_000_000;
    return `${millions % 1 === 0 ? millions : millions.toFixed(1)}M`;
  }
  if (tokens >= 1_000) {
    const thousands = tokens / 1_000;
    return `${thousands % 1 === 0 ? thousands : thousands.toFixed(0)}K`;
  }
  return `${tokens}`;
}

export function computeMountComparison(
  currentModelId: string,
  targetSpotlight: SpotlightModelItem
): MountComparison {
  const currentSpec =
    DEFAULT_CURRENT_MODEL_SPECS[currentModelId] || DEFAULT_CURRENT_MODEL_SPECS.default;
  const contextDeltaTokens = targetSpotlight.contextWindow - currentSpec.context;
  const currentBasePrice = currentSpec.priceInput > 0 ? currentSpec.priceInput : 1.0;
  const priceDeltaPercent = Math.round(
    ((targetSpotlight.pricingInputPerM - currentBasePrice) / currentBasePrice) * 100
  );

  return {
    currentModelId,
    targetModelId: targetSpotlight.modelId,
    currentContextWindow: currentSpec.context,
    targetContextWindow: targetSpotlight.contextWindow,
    contextDeltaTokens,
    priceDeltaPercent,
    supportsVision: targetSpotlight.highlightBadges.includes('multimodal'),
    supportsReasoning: targetSpotlight.highlightBadges.includes('reasoning'),
  };
}

export function isSpotlightDismissed(
  record: DismissRecord | undefined,
  now = Date.now(),
  ttlMs = 24 * 60 * 60 * 1000
): boolean {
  if (!record) {
    return false;
  }
  if (record.permanent) {
    return true;
  }
  return now - record.dismissedAt < ttlMs;
}

export function filterAvailableSpotlights(
  items: SpotlightModelItem[],
  dismissedRecords: Record<string, DismissRecord>,
  now = Date.now()
): SpotlightModelItem[] {
  return items.filter((item) => {
    const record = dismissedRecords[item.id];
    return !isSpotlightDismissed(record, now);
  });
}
