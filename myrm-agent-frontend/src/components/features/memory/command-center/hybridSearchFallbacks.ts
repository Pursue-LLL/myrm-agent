/**
 * Fallback mock data and presets for DualEngineHybridSearchStudioCard.
 */

import type {
  AdaptiveRrfConfigDTO,
  HybridEngineStatsDTO,
  HybridSearchResultDTO,
} from '@/services/memory/hybridSearch';

export const INITIAL_ADAPTIVE_RRF_CONFIG: AdaptiveRrfConfigDTO = {
  rrf_k: 60,
  fts_weight: 1.0,
  vector_weight: 1.0,
  importance_weight: 0.3,
  half_life_seconds: 86400,
  apply_recency_decay: true,
};

export const INITIAL_HYBRID_STATS: HybridEngineStatsDTO = {
  total_items: 128,
  synonym_terms_count: 42,
  dense_vector_available: true,
  active_mode: 'hybrid_rrf',
  db_path: 'local/storage/hybrid_memory_fts5.db',
  circuit_breaker: {
    state: 'closed',
    failure_count: 0,
    consecutive_successes: 12,
    last_failure_time: 0,
    tripped_count: 0,
  },
  last_updated: new Date().toISOString(),
};

export const INITIAL_SEARCH_RESULTS: HybridSearchResultDTO[] = [
  {
    item_id: 'mem_arch_001',
    title: 'SQLite FTS5 与 Vector 双引擎检索架构',
    content: '采用本地 SQLite unicode61 分词进行亚毫秒级 BM25 召回，结合向量余弦相似度与 RRF 融合。',
    score: 0.9421,
    source_channel: 'rrf_hybrid',
    rank: 1,
    matched_terms: ['双引擎', 'FTS5', 'RRF'],
    importance: 0.9,
    recency_factor: 0.985,
    is_degraded: false,
    degradation_reason: '',
  },
  {
    item_id: 'mem_resilience_002',
    title: '三态自愈断路器降级保护机制',
    content: '当向量嵌入服务发生超时或网络抖动时，断路器进入 OPEN 状态，实现低于 0.1ms 的极速平滑降级。',
    score: 0.8215,
    source_channel: 'rrf_hybrid',
    rank: 2,
    matched_terms: ['断路器', '自愈', '降级'],
    importance: 0.85,
    recency_factor: 0.92,
    is_degraded: false,
    degradation_reason: '',
  },
  {
    item_id: 'mem_ebbinghaus_003',
    title: '艾宾浩斯记忆时间衰减调优',
    content: '根据最后交互时间计算指数衰减因子，确保长期稳定记忆与近期活跃工作记忆在检索中获得自适应权重。',
    score: 0.748,
    source_channel: 'fts',
    rank: 3,
    matched_terms: ['时间衰减', '艾宾浩斯'],
    importance: 0.7,
    recency_factor: 0.86,
    is_degraded: false,
    degradation_reason: '',
  },
];
