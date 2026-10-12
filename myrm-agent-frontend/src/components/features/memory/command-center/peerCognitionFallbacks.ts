/**
 * [INPUT]
 * @/services/memory/peerCognition (DTO types)
 *
 * [OUTPUT]
 * Realistic fallback datasets for Item 110:
 * PeerCentricEntityGraphAndAgentPersonaCardSuite.
 *
 * [POS]
 * Command-center fallback datasets for offline resilience and testing.
 * Strict typing applied: No `any` types allowed. Single file < 250 lines.
 */

import type {
  PeerCognitionProjectionDTO,
  PeerIdentityDTO,
  PeerPersonaCardDTO,
  PeerRelationEdgeDTO,
} from '@/services/memory/peerCognition';

export const FALLBACK_PEERS: PeerIdentityDTO[] = [
  {
    peer_id: 'user_alice',
    peer_type: 'user_peer',
    display_name: 'Alice Liu',
    role_title: '首席架构师 (Lead Architect)',
    avatar_or_icon: 'user-crown',
    created_at: '2026-09-17T08:00:00Z',
    last_seen_at: '2026-10-08T06:00:00Z',
  },
  {
    peer_id: 'agent_coder',
    peer_type: 'agent_peer',
    display_name: 'CoderAgent',
    role_title: '后端全栈实现智能体 (Backend Implementer)',
    avatar_or_icon: 'bot-terminal',
    created_at: '2026-09-17T08:10:00Z',
    last_seen_at: '2026-10-08T06:15:00Z',
  },
  {
    peer_id: 'reviewer_bob',
    peer_type: 'reviewer_peer',
    display_name: 'Bob Security',
    role_title: '安全合规审查者 (SecOps Auditor)',
    avatar_or_icon: 'shield-check',
    created_at: '2026-09-18T10:00:00Z',
    last_seen_at: '2026-10-08T05:30:00Z',
  },
  {
    peer_id: 'proj_myrm_core',
    peer_type: 'project_peer',
    display_name: 'Myrm Harness Core',
    role_title: '通用执行引擎框架项目实体',
    avatar_or_icon: 'box-archive',
    created_at: '2026-09-15T09:00:00Z',
    last_seen_at: '2026-10-08T06:20:00Z',
  },
];

export const FALLBACK_CARDS: Record<string, PeerPersonaCardDTO> = {
  user_alice: {
    peer_id: 'user_alice',
    peer_type: 'user_peer',
    display_name: 'Alice Liu',
    core_responsibilities: [
      '框架宏观架构演进与设计规范把控',
      '跨模块边界清晰化与去技术债决策',
      '关键方案最终仲裁与演进路径确认',
    ],
    decision_style: 'quality-first (零容忍屎山，纯净重构优先)',
    standing_preferences: {
      type_hints: '严禁使用 Any，必须使用强类型',
      max_file_lines: '单文件严格控制在 400 行以内',
      test_coverage: '必须提供 100% 绿灯自动化单测与边界断言',
    },
    interaction_count: 86,
    success_rate: 0.98,
    trust_score: 0.99,
    summary_digest:
      'Role: Alice Liu (user_peer). Focused on 宏观架构演进与去技术债. Decision style: quality-first with trust 0.99. Key preferences: 严禁 Any; 单文件严格不超过400行.',
    updated_at: '2026-10-08T06:15:00Z',
  },
  agent_coder: {
    peer_id: 'agent_coder',
    peer_type: 'agent_peer',
    display_name: 'CoderAgent',
    core_responsibilities: [
      'Harness 框架与 Server 业务全栈代码忠实落地',
      '单测与 Lint 自动化闭环测试',
      '严格遵照系统规范切分模块与文件',
    ],
    decision_style: 'rigorous-execution (按证据办事，第一性原理分析)',
    standing_preferences: {
      feedback_loop: '每轮子任务完成后主动发起交互式反馈',
      refactor_rule: '禁止向后兼容牺牲质量，消除冗余',
    },
    interaction_count: 142,
    success_rate: 0.96,
    trust_score: 0.97,
    summary_digest:
      'Role: CoderAgent (agent_peer). Focused on 全栈代码忠实落地与单测闭环. Decision style: rigorous-execution with trust 0.97.',
    updated_at: '2026-10-08T06:20:00Z',
  },
  reviewer_bob: {
    peer_id: 'reviewer_bob',
    peer_type: 'reviewer_peer',
    display_name: 'Bob Security',
    core_responsibilities: [
      '凭据泄露防范与敏感路径隔离审计',
      '沙箱逃逸防御与破坏性 Shell 拦截',
    ],
    decision_style: 'defensive-strict (安全第一，阻断高危提权)',
    standing_preferences: {
      git_safety: '禁止 git reset/checkout 等破坏性命令',
      path_boundary: '禁止修改当前项目目录以外的任何文件',
    },
    interaction_count: 53,
    success_rate: 1.0,
    trust_score: 0.99,
    summary_digest:
      'Role: Bob Security (reviewer_peer). Focused on 凭据防护与高危命令阻断. Decision style: defensive-strict with trust 0.99.',
    updated_at: '2026-10-08T05:30:00Z',
  },
  proj_myrm_core: {
    peer_id: 'proj_myrm_core',
    peer_type: 'project_peer',
    display_name: 'Myrm Harness Core',
    core_responsibilities: [
      '提供无业务耦合的通用 Agent 执行引擎能力',
      '单机沙箱内原生运行，无多租户干扰',
    ],
    decision_style: 'framework-isolated (层层独立，严禁反向依赖)',
    standing_preferences: {
      license: 'MIT 开源',
      mcp_mode: '直接工具调用 + 渐进式披露，禁止 catalog_invoke 第三路径',
    },
    interaction_count: 320,
    success_rate: 0.99,
    trust_score: 1.0,
    summary_digest:
      'Role: Myrm Harness Core (project_peer). Focused on 通用执行引擎与单机沙箱. Decision style: framework-isolated with trust 1.00.',
    updated_at: '2026-10-08T06:20:00Z',
  },
};

export const FALLBACK_EDGES: PeerRelationEdgeDTO[] = [
  {
    edge_id: 'edge_arch_assert_01',
    source_peer_id: 'user_alice',
    target_entity_id: 'fact_pure_refactor_no_backcompat',
    target_is_peer: false,
    relation_kind: 'asserts',
    context_note: '明确规定禁止向后兼容牺牲代码质量，必须前瞻重构消除技术债',
    weight: 1.0,
    created_at: '2026-09-17T08:30:00Z',
  },
  {
    edge_id: 'edge_sec_approve_02',
    source_peer_id: 'reviewer_bob',
    target_entity_id: 'fact_pure_refactor_no_backcompat',
    target_is_peer: false,
    relation_kind: 'approves',
    context_note: '安全审查确认纯净重构规则符合代码审计与资产防泄露要求',
    weight: 0.98,
    created_at: '2026-09-18T11:00:00Z',
  },
  {
    edge_id: 'edge_collab_coder_03',
    source_peer_id: 'user_alice',
    target_entity_id: 'agent_coder',
    target_is_peer: true,
    relation_kind: 'collaborates_with',
    context_note: '首席架构师与全栈实现智能体结对编程执行复杂工程任务',
    weight: 0.95,
    created_at: '2026-09-17T09:00:00Z',
  },
  {
    edge_id: 'edge_gov_proj_04',
    source_peer_id: 'proj_myrm_core',
    target_entity_id: 'agent_coder',
    target_is_peer: true,
    relation_kind: 'governs',
    context_note: 'Harness 框架设计原则 (FRAMEWORK_DESIGN_PRINCIPLES.md) 约束编码边界',
    weight: 1.0,
    created_at: '2026-09-15T10:00:00Z',
  },
];

export const FALLBACK_PROJECTION: PeerCognitionProjectionDTO = {
  formatted_prompt_block: `<!-- [PEER SOCIAL COGNITION CONTEXT] -->
### 当前协作参与者社会认知对齐
- **@user_peer Alice Liu** (首席架构师): 聚焦宏观架构演进与去技术债 | 决策风格: quality-first | 关键偏好: 严禁 Any; 单文件严格不超过400行
- **@agent_peer CoderAgent** (全栈实现智能体): 聚焦代码忠实落地与单测闭环 | 决策风格: rigorous-execution | 信任度: 0.97
- **@reviewer_peer Bob Security** (安全合规审查者): 聚焦高危命令防御与沙箱隔离 | 决策风格: defensive-strict
- **@project_peer Myrm Harness Core**: 约束执行引擎边界与直接工具调用原则
<!-- [/PEER SOCIAL COGNITION CONTEXT] -->`,
  token_cost_estimate: 78,
  targeted_peers: ['user_alice', 'agent_coder', 'reviewer_bob', 'proj_myrm_core'],
};
