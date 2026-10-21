/**
 * [INPUT]
 * @/services/memory/budgetPacking
 *
 * [OUTPUT]
 * Constants: FALLBACK_CANDIDATES, FALLBACK_BUDGET, FALLBACK_PACKED_RESULT, FALLBACK_ACCOUNTING
 *
 * [POS]
 * Fallback dataset for Budget Greedy Marginal Value Recall Packing Suite (Item 122 P2).
 * Strict typing applied: No `any` types allowed. Single file < 150 lines.
 */

import type {
  BilledTokenBudgetDTO,
  PackedRecallResultDTO,
  PackingCandidateDTO,
  TokenAccountingReportDTO,
} from '@/services/memory/budgetPacking';

export const FALLBACK_CANDIDATES: PackingCandidateDTO[] = [
  {
    id: 'cand-01',
    content: '核心架构质量红线：模块与方法必须职责单一，单个源码文件行数原则上不超过400行。',
    relevance_score: 0.96,
    confidence_score: 1.0,
    billed_tokens: 38,
    storage_tokens: 88,
    domain_tags: ['architecture', 'code_quality'],
    source_session_id: 'session_arch_001',
  },
  {
    id: 'cand-02',
    content: '模块设计规范：单个文件代码行数严格控制在400行以内，超过时必须主动拆分。',
    relevance_score: 0.93,
    confidence_score: 1.0,
    billed_tokens: 36,
    storage_tokens: 84,
    domain_tags: ['architecture', 'duplicate'],
    source_session_id: 'session_arch_002',
  },
  {
    id: 'cand-03',
    content: '类型约束红线：严格禁止使用 any 类型，必须使用具体明确的 Type Hints。',
    relevance_score: 0.91,
    confidence_score: 1.0,
    billed_tokens: 32,
    storage_tokens: 76,
    domain_tags: ['typescript', 'python', 'typing'],
    source_session_id: 'session_quality_003',
  },
  {
    id: 'cand-04',
    content: '工程门禁红线：所有新增与变更必须通过全量单测与代码检查门禁，全绿方可交付。',
    relevance_score: 0.88,
    confidence_score: 1.0,
    billed_tokens: 35,
    storage_tokens: 82,
    domain_tags: ['engineering', 'testing'],
    source_session_id: 'session_ci_004',
  },
  {
    id: 'cand-05',
    content: '冗余历史说明片段：关于早期系统原型尝试向后兼容方案的背景调研纪要（陈旧信息）。',
    relevance_score: 0.52,
    confidence_score: 0.6,
    billed_tokens: 75,
    storage_tokens: 140,
    domain_tags: ['legacy', 'deprecated'],
    source_session_id: 'session_legacy_005',
  },
];

export const FALLBACK_BUDGET: BilledTokenBudgetDTO = {
  max_billed_tokens: 120,
  diversity_penalty_lambda: 0.75,
  min_marginal_value_threshold: 0.05,
  max_redundancy_threshold: 0.45,
  max_items_limit: 5,
  allow_greedy_backfill: true,
};

export const FALLBACK_ACCOUNTING: TokenAccountingReportDTO = {
  total_candidates_examined: 5,
  items_packed_count: 3,
  items_dropped_count: 2,
  billed_tokens_spent: 105,
  billed_tokens_budget: 120,
  billed_tokens_remaining: 15,
  storage_tokens_total: 470,
  storage_tokens_saved: 224,
  budget_utilization_pct: 87.5,
  redundant_tokens_filtered: 36,
  average_marginal_density: 0.0264,
};

export const FALLBACK_PACKED_RESULT: PackedRecallResultDTO = {
  packed_items: [
    {
      candidate: FALLBACK_CANDIDATES[0],
      metrics: {
        base_utility: 0.96,
        redundancy_score: 0.0,
        marginal_info_gain: 1.0,
        marginal_value: 0.96,
        marginal_value_density: 0.02526,
      },
      order_index: 0,
      cumulative_billed_tokens: 38,
    },
    {
      candidate: FALLBACK_CANDIDATES[2],
      metrics: {
        base_utility: 0.91,
        redundancy_score: 0.08,
        marginal_info_gain: 0.94,
        marginal_value: 0.8554,
        marginal_value_density: 0.02673,
      },
      order_index: 1,
      cumulative_billed_tokens: 70,
    },
    {
      candidate: FALLBACK_CANDIDATES[3],
      metrics: {
        base_utility: 0.88,
        redundancy_score: 0.09,
        marginal_info_gain: 0.9325,
        marginal_value: 0.8206,
        marginal_value_density: 0.02345,
      },
      order_index: 2,
      cumulative_billed_tokens: 105,
    },
  ],
  dropped_candidates: [
    {
      candidate: FALLBACK_CANDIDATES[1],
      metrics: {
        base_utility: 0.93,
        redundancy_score: 0.72,
        marginal_info_gain: 0.46,
        marginal_value: 0.4278,
        marginal_value_density: 0.01188,
      },
      reason: 'redundancy_suppressed',
    },
    {
      candidate: FALLBACK_CANDIDATES[4],
      metrics: {
        base_utility: 0.312,
        redundancy_score: 0.05,
        marginal_info_gain: 0.9625,
        marginal_value: 0.3003,
        marginal_value_density: 0.00400,
      },
      reason: 'budget_exhausted',
    },
  ],
  accounting: FALLBACK_ACCOUNTING,
  composed_prompt_block: `<recalled_memories billed_tokens="105" budget="120" count="3">
  <memory_item id="cand-01" rank="1" utility="0.960" tokens="38" domain="architecture code_quality">
    核心架构质量红线：模块与方法必须职责单一，单个源码文件行数原则上不超过400行。
  </memory_item>
  <memory_item id="cand-03" rank="2" utility="0.855" tokens="32" domain="typescript python typing">
    类型约束红线：严格禁止使用 any 类型，必须使用具体明确的 Type Hints。
  </memory_item>
  <memory_item id="cand-04" rank="3" utility="0.821" tokens="35" domain="engineering testing">
    工程门禁红线：所有新增与变更必须通过全量单测与代码检查门禁，全绿方可交付。
  </memory_item>
</recalled_memories>`,
  active_mode: 'greedy_marginal_knapsack',
};
