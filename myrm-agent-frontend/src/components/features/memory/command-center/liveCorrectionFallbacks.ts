/**
 * [INPUT]
 * @/services/memory::(Live Correction DTOs)
 *
 * [OUTPUT]
 * Constants: FALLBACK_CANDIDATES, FALLBACK_SAMPLE_UTTERANCES,
 *            FALLBACK_RECEIPT, FALLBACK_HISTORY, FALLBACK_STATUS
 *
 * [POS]
 * High-fidelity fallbacks for Item 128 Natural Language Memory Feedback & Live Correction Suite.
 * Guarantees resilient WebUI preview and uninterrupted offline experience.
 * Strict typing applied: Zero `any` types. Single file < 200 lines.
 */

import type {
  CorrectionAckReceiptDTO,
  LiveCorrectionHistoryResponse,
  LiveCorrectionStatusResponse,
  TargetNodeCandidateDTO,
} from '@/services/memory';

export const FALLBACK_CANDIDATES: TargetNodeCandidateDTO[] = [
  {
    memory_id: 'mem_pref_beverage',
    content: '用户早晨和下午喜欢饮用 美式咖啡（不加糖奶）',
    cube_id: 'user_preference',
    match_score: 1.0,
    attributes: { category: 'preference', status: 'active' },
  },
  {
    memory_id: 'mem_fact_database',
    content: '系统主业务存储架构采用 MySQL 8.0 主从副本集群',
    cube_id: 'architecture_facts',
    match_score: 1.0,
    attributes: { category: 'fact', status: 'active' },
  },
  {
    memory_id: 'mem_rule_commit',
    content: 'Git 提交前允许直接在 main 分支提交代码并推送',
    cube_id: 'engineering_rules',
    match_score: 1.0,
    attributes: { category: 'rule', status: 'active' },
  },
  {
    memory_id: 'mem_cred_api_token',
    content: '测试环境第三方集成 API Key 凭证为 test_sec_abc12345',
    cube_id: 'ephemeral_keys',
    match_score: 1.0,
    attributes: { category: 'secret', status: 'deprecated' },
  },
];

export const FALLBACK_SAMPLE_UTTERANCES: string[] = [
  '我不喜欢美式咖啡，换成燕麦拿铁',
  '其实主数据库并非 MySQL，而是 SQLite WAL 嵌入式存储',
  '以后禁止直接向 main 分支推送，必须走 PR 代码审查',
  '撤回之前关于 API Key 的记忆记录',
];

export const FALLBACK_RECEIPT: CorrectionAckReceiptDTO = {
  success: true,
  ack_message: '已为您更正偏好：由「美式咖啡」调整为「燕麦拿铁」，后续对话将以此为准。',
  intent: 'preference_update',
  slot: {
    corrected_value: '燕麦拿铁',
    negated_value: '美式咖啡',
    subject: null,
    intent: 'preference_update',
    confidence: 0.95,
    raw_utterance: '我不喜欢美式咖啡，换成燕麦拿铁',
  },
  mutated_record: {
    action: 'supersede',
    target_memory_id: 'mem_pref_beverage',
    new_memory_id: 'mem_corr_8a9f2e',
    status: 'applied',
    superseded_content: '用户早晨和下午喜欢饮用 美式咖啡（不加糖奶）',
    new_content: '燕麦拿铁',
    audit_trail: {
      superseded_by: 'mem_corr_8a9f2e',
      previous_id: 'mem_pref_beverage',
      match_score: '0.95',
      utterance: '我不喜欢美式咖啡，换成燕麦拿铁',
    },
    timestamp: '2026-10-08T13:40:00Z',
  },
  processing_ms: 12.8,
};

export const FALLBACK_HISTORY: LiveCorrectionHistoryResponse = {
  history: [
    {
      action: 'supersede',
      target_memory_id: 'mem_pref_beverage',
      new_memory_id: 'mem_corr_8a9f2e',
      status: 'applied',
      superseded_content: '用户早晨和下午喜欢饮用 美式咖啡（不加糖奶）',
      new_content: '燕麦拿铁',
      audit_trail: {
        reason: 'user_correction',
        utterance: '我不喜欢美式咖啡，换成燕麦拿铁',
      },
      timestamp: '2026-10-08T13:40:00Z',
    },
  ],
  total: 1,
};

export const FALLBACK_STATUS: LiveCorrectionStatusResponse = {
  service_status: 'ready',
  candidates_count: 4,
  mutations_count: 1,
};
