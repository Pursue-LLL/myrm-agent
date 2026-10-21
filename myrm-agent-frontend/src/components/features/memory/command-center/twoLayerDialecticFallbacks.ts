/**
 * [INPUT]
 * @/services/memory/twoLayerDialectic (Types & DTOs)
 *
 * [OUTPUT]
 * Deterministic baseline datasets for Two-Layer Dialectic Suite offline resilience and unit tests.
 *
 * [POS]
 * Command-center fallbacks for Item 112.
 * Strict typing applied: No `any` types allowed. Single file < 160 lines.
 */

import type {
  BaseContextPayloadDTO,
  DialecticCadenceConfigDTO,
  DialecticConflictCandidateDTO,
  DialecticReconciliationResultDTO,
  TwoLayerContextInjectionResultDTO,
} from '@/services/memory/twoLayerDialectic';

export const FALLBACK_CADENCE_CONFIG: DialecticCadenceConfigDTO = {
  context_cadence: 5,
  dialectic_cadence: 3,
  dialectic_depth: 3,
  dialectic_reasoning_level: 'standard',
};

export const FALLBACK_BASE_CONTEXT: BaseContextPayloadDTO = {
  session_summary:
    '当前阶段聚焦全栈三层架构落地与代码质量红线：单文件行数上限、强类型约束与测试门禁。',
  standing_peer_cards: [
    'Alice Liu (前端架构负责人 · 严格无Any · 强类型契约守护者)',
    'DevBot (全栈重构助手 · 纯净重构先锋 · 拒绝向后兼容技术债)',
    'ArchReviewer (安全审计哨兵 · a11y与单文件行数硬门禁执行官)',
  ],
  cache_control_hash: 'a9f2e4b81c7d3e05',
  refreshed_at_turn: 5,
  created_at: '2026-10-08T06:30:00.000Z',
};

export const FALLBACK_CONFLICTS: DialecticConflictCandidateDTO[] = [
  {
    statement_a: '系统采用 SQLite 作为本地单机轻量级存储引擎，追求免配置开箱即用。',
    statement_b: '在分布式高并发云托管生产集群中，存储层切换至 PostgreSQL 架构。',
    subject_domain: 'Database Architecture',
    conflict_score: 0.95,
  },
  {
    statement_a: '为了兼顾旧客户端，需保留部分向后兼容适配层。',
    statement_b: '代码质量红线强调纯净重构：禁止向后兼容，绝不牺牲质量遗留技术债。',
    subject_domain: 'Refactoring Philosophy',
    conflict_score: 0.92,
  },
  {
    statement_a: '向量索引依赖本地 sqlite-vec 扩展。',
    statement_b: '大规模知识检索切换至专用 Qdrant 向量集群。',
    subject_domain: 'Vector Store Strategy',
    conflict_score: 0.88,
  },
];

export const FALLBACK_RECONCILIATION_RESULTS: DialecticReconciliationResultDTO[] = [
  {
    passes_executed: ['inspection', 'synthesis', 'reconciliation'],
    resolved_statement:
      '在当前生产集群模式下，采纳 PostgreSQL 作为主存储；本地开发与单机模式由配置驱动保留 SQLite 隔离。',
    superseded_statements: [
      '系统采用 SQLite 作为本地单机轻量级存储引擎，追求免配置开箱即用。',
    ],
    confidence: 0.96,
    rationale:
      'Pass 0 审查确认两者为不同部署环境需求；Pass 1 综合两者边界；Pass 2 确立环境驱动决策，消解二义性。',
  },
  {
    passes_executed: ['inspection', 'synthesis', 'reconciliation'],
    resolved_statement:
      '严格执行纯净重构红线：当前模块代码全面升级为现代化强类型规范，禁止残留向后兼容冗余包袱。',
    superseded_statements: ['为了兼顾旧客户端，需保留部分向后兼容适配层。'],
    confidence: 0.98,
    rationale:
      '架构契约具有最高优先级，向前演进收益远大于历史兼容包袱，决议执行彻底清理。',
  },
];

export const FALLBACK_INJECTION_RESULT: TwoLayerContextInjectionResultDTO = {
  layer1_base_context:
    '<base_context cache_hash="a9f2e4b81c7d3e05" session="sess_main" turn="5">\n  <session_summary>当前阶段聚焦全栈三层架构落地与代码质量红线治理：强制单文件<400行、严禁Any类型。</session_summary>\n  <peer_cards>Alice Liu, DevBot, ArchReviewer</peer_cards>\n</base_context>',
  layer2_dialectic_block:
    '<dialectic_reconciliation>\n  <resolution>在当前生产集群模式下，采纳 PostgreSQL 作为主存储；本地开发与单机模式由配置驱动保留 SQLite 隔离。</resolution>\n  <rationale>Pass 0-2 辩证调和消除存储选型冲突。</rationale>\n</dialectic_reconciliation>',
  injected_position: 'user_message_tail',
  is_cache_safe: true,
  token_overhead: 86,
};
