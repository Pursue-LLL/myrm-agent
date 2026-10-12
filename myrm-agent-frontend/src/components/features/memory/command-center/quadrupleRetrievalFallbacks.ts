/**
 * [INPUT]
 * @/services/memory::(Quadruple Retrieval DTOs)
 *
 * [OUTPUT]
 * Constants: FALLBACK_RETRIEVAL_STATS, FALLBACK_PARSED_GOAL, FALLBACK_SEARCH_RESPONSE
 *
 * [POS]
 * High-fidelity fallbacks for Item 127 Goal-Driven Quadruple Retrieval & Reasoner Suite.
 * Guarantees resilient WebUI preview and uninterrupted offline experience.
 * Strict typing applied: Zero `any` types. Single file < 200 lines.
 */

import type {
  ParsedTaskGoalDTO,
  QuadrupleRetrievalStatsDTO,
  QuadrupleSearchResponse,
} from '@/services/memory';

export const FALLBACK_RETRIEVAL_STATS: QuadrupleRetrievalStatsDTO = {
  total_indexed_memories: 142,
  active_channels_count: 4,
  average_latency_ms: 4.2,
  channel_weights: {
    graph: 1.15,
    vector: 1.0,
    lexical: 0.9,
    metadata: 0.85,
  },
};

export const FALLBACK_PARSED_GOAL: ParsedTaskGoalDTO = {
  goal_id: 'goal_arch_std_901',
  original_query: '帮我查一下项目关于单文件行数限制和 TypeScript any 类型的架构红线要求',
  explicit_intent: 'technical_standard',
  target_entities: ['架构红线', '单文件行数限制', 'any类型', 'TypeScript规范'],
  extracted_keywords: ['单文件', '400行', 'any', 'type', 'hints', '架构', '红线'],
  metadata_filters: {
    domain: 'architecture',
    tier: 'p0',
    status: 'active',
  },
  temporal_constraints: null,
  confidence: 0.98,
};

export const FALLBACK_SEARCH_RESPONSE: QuadrupleSearchResponse = {
  query: '帮我查一下项目关于单文件行数限制和 TypeScript any 类型的架构红线要求',
  parsed_goal: FALLBACK_PARSED_GOAL,
  channel_hits_count: {
    graph: 2,
    vector: 4,
    lexical: 3,
    metadata: 2,
  },
  fused_candidates_count: 5,
  final_hits: [
    {
      memory_id: 'mem_arch_001',
      content: '[架构红线] 单文件原则上不超过400行，严禁使用 any 类型，必须使用具体 Type Hints。',
      final_rank: 1,
      final_score: 1.84,
      channels_hit: ['graph', 'vector', 'lexical', 'metadata'],
      reasoner_decision: 'boost',
      rationale:
        'Reasoner boosted (+35%) candidate matching explicit entities (架构红线, any类型) with 4-way channel consensus.',
      metadata: {
        domain: 'architecture',
        scope: 'core',
        tier: 'p0',
        status: 'active',
      },
    },
    {
      memory_id: 'mem_gate_002',
      content: '[门禁规范] 提交前必须执行 check-a11y-ratchet.mjs 确保 0 a11y 违规，严禁使用非语义 div role 标签。',
      final_rank: 2,
      final_score: 1.25,
      channels_hit: ['vector', 'lexical'],
      reasoner_decision: 'keep',
      rationale:
        'Candidate preserved via consensus across channels (vector, lexical) with standard relevance to frontend engineering standards.',
      metadata: {
        domain: 'frontend',
        scope: 'gate',
        tier: 'p0',
        status: 'active',
      },
    },
    {
      memory_id: 'mem_proto_004',
      content: '[检索协议] QuadrupleParallelRetriever 同时激发 Graph, Vector, Lexical(FTS5) 及 Metadata 四路通道并行命中。',
      final_rank: 3,
      final_score: 1.12,
      channels_hit: ['graph', 'lexical'],
      reasoner_decision: 'keep',
      rationale:
        'Graph entity overlap on retrieval engine components and keyword matching on quadruple protocols.',
      metadata: {
        domain: 'retrieval',
        scope: 'engine',
        tier: 'p1',
        status: 'active',
      },
    },
    {
      memory_id: 'mem_legacy_003',
      content: '[旧版方案/已废弃] 旧系统曾使用集中式全量检索 router proxy，已被 MemOS 目标驱动四路检索彻底取代。',
      final_rank: 4,
      final_score: 0.38,
      channels_hit: ['lexical'],
      reasoner_decision: 'penalize_stale',
      rationale:
        'Reasoner applied staleness penalty (-65%) due to deprecated/superseded marker: status=deprecated.',
      metadata: {
        domain: 'legacy',
        scope: 'deprecated',
        status: 'deprecated',
      },
    },
  ],
  latency_ms: 3.8,
  created_at: '2026-10-08T12:00:00Z',
};
