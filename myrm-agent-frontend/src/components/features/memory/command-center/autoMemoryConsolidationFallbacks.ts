/**
 * [INPUT]
 * @/services/memory/autoMemoryConsolidation::AutoMemoryGatingConfigDTO, OverallGatingReportDTO, SixDimensionalMemoryArtifactDTO
 *
 * [OUTPUT]
 * FALLBACK_AUTO_CONSOLIDATION_CONFIG, FALLBACK_GATING_REPORT_ADMITTED,
 * FALLBACK_GATING_REPORT_REJECTED, FALLBACK_SIX_DIMENSIONAL_ARTIFACT,
 * SAMPLE_CONVERSATION_PRESETS
 *
 * [POS]
 * Deterministic fallback mocks and presets for Item 123 auto-consolidation studio.
 * Strict typing: No `any` types. Single file < 200 lines.
 */

import type {
  AutoMemoryGatingConfigDTO,
  OverallGatingReportDTO,
  SixDimensionalMemoryArtifactDTO,
} from '@/services/memory/autoMemoryConsolidation';

export const FALLBACK_AUTO_CONSOLIDATION_CONFIG: AutoMemoryGatingConfigDTO = {
  enabled: true,
  idle_timeout_seconds: 900.0,
  min_turn_count: 3,
  min_info_density: 0.35,
  min_remaining_budget_tokens: 1000,
  max_consolidation_cost_ratio: 0.25,
};

export const FALLBACK_GATING_REPORT_ADMITTED: OverallGatingReportDTO = {
  session_id: 'sess-live-9421',
  should_consolidate: true,
  turn_decision: {
    passed: true,
    turn_count: 4,
    info_density: 0.685,
    reason: 'Passed turn & info gate: 4 turns, density 0.685 >= 0.350.',
  },
  budget_decision: {
    passed: true,
    remaining_tokens: 14200,
    estimated_cost_tokens: 780,
    cost_ratio: 0.0549,
    reason: 'Passed budget gate: remaining 14200 tokens, cost 780 (5.49% <= 25.00%).',
  },
  idle_state: {
    session_id: 'sess-live-9421',
    idle_seconds: 960.0,
    idle_threshold_seconds: 900.0,
    is_idle_triggered: true,
    reason: 'Session inactive for 960.0s (threshold: 900.0s). Background consolidation eligible.',
  },
  final_rationale: 'All gates cleared. Automated background memory consolidation approved.',
};

export const FALLBACK_GATING_REPORT_REJECTED: OverallGatingReportDTO = {
  session_id: 'sess-chitchat-104',
  should_consolidate: false,
  turn_decision: {
    passed: false,
    turn_count: 1,
    info_density: 0.12,
    reason: 'Conversation too brief: 1 turns (required: 3). Bypassing low-value memory generation.',
  },
  budget_decision: {
    passed: true,
    remaining_tokens: 8500,
    estimated_cost_tokens: 420,
    cost_ratio: 0.0494,
    reason: 'Passed budget gate: remaining 8500 tokens, cost 420 (4.94% <= 25.00%).',
  },
  idle_state: {
    session_id: 'sess-chitchat-104',
    idle_seconds: 120.0,
    idle_threshold_seconds: 900.0,
    is_idle_triggered: false,
    reason: 'Session still active or below idle threshold (120.0s < 900.0s).',
  },
  final_rationale: 'Waiting for idle timeout; Conversation too brief: 1 turns (required: 3).',
};

export const FALLBACK_SIX_DIMENSIONAL_ARTIFACT: SixDimensionalMemoryArtifactDTO = {
  artifact_id: 'art-6d-7f8e3b2a1c0d',
  session_id: 'sess-live-9421',
  created_at_iso: '2026-10-08T03:20:00Z',
  working_directory: '/Users/yululiu/projects/AI/open-perplexity/myrm-agent-harness',
  key_topics: ['sqlite', 'wal', 'knapsack', 'gating', 'pydantic', 'types'],
  user_preferences: [
    'Strict type hints throughout, zero Any types allowed.',
    'Single file length strictly capped under 400 lines.',
    'Forbid backward compatibility shims, pure refactoring standard.',
  ],
  reusable_domain_knowledge: [
    'SQLite concurrent writes require PRAGMA journal_mode=WAL and busy_timeout=5000.',
    'Greedy backfilling elevates context utilization from 58% to 88% under hard token caps.',
  ],
  failure_lessons: [
    'AsyncClient unclosed connection pool leak avoided by using async with context block.',
    'Empty lexical diversity on short text avoided with dynamic volume scaling factor.',
  ],
  tool_calling_patterns: [
    'run_command: invoked 5 time(s)',
    'replace_file_content: invoked 3 time(s)',
    'view_file: invoked 2 time(s)',
  ],
  token_cost: 620,
  summary_digest:
    'Workspace: myrm-agent-harness. Preserved 3 user preference rules. Distilled 2 architectural insights and 2 postmortem lesson traps. Tool Usage: run_command 5 times.',
};

export const SAMPLE_CONVERSATION_PRESETS = [
  {
    name: '架构重构与避坑会话 (高信息密度 · 满足准入)',
    messages: [
      { role: 'user', content: '重构记忆存储层，严格禁止 Any 类型，必须单文件少于 400 行。' },
      { role: 'assistant', content: '收到，采用 Clean Architecture 门面模式解耦 Harness 与业务层。' },
      { role: 'user', content: '遇到 SQLite 并发写入锁超时错误，如何根本自愈？' },
      { role: 'assistant', content: '通过配置 PRAGMA journal_mode=WAL 与 busy_timeout=5000 彻底化解锁争用。' },
    ],
    toolCalls: ['run_command', 'replace_file_content', 'run_command'],
    idleSeconds: 960,
    remainingTokens: 15000,
  },
  {
    name: '日常闲聊寒暄 (极短轮数 · 自动拦截)',
    messages: [
      { role: 'user', content: '你好，在吗？' },
      { role: 'assistant', content: '在的，请问有什么可以帮您？' },
    ],
    toolCalls: [],
    idleSeconds: 150,
    remainingTokens: 12000,
  },
  {
    name: '额度告急长对话 (预算不足门禁 · 安全挂起)',
    messages: [
      { role: 'user', content: '帮我分析这一整套分布式系统的拓扑并输出架构图。' },
      { role: 'assistant', content: '已解析所有服务依赖关系图谱。' },
      { role: 'user', content: '继续分析所有数据表外键约束和级联删除影响。' },
      { role: 'assistant', content: '数据表分析已完成，建议移除双向级联删除。' },
    ],
    toolCalls: ['view_file', 'run_command'],
    idleSeconds: 1200,
    remainingTokens: 600, // < 1000 floor
  },
];
