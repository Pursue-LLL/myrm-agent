/**
 * Fallback fixtures and offline simulation for Proactive Past-Pitfall Alert & Decision Assist.
 * Provides high-fidelity mock data for unit tests and offline command-center runtime.
 */

import {
  PitfallAlertCardDTO,
  PitfallAlertStatusResponse,
  PitfallEvaluationResponse,
} from '@/services/memory/decisionAssist';

export const mockPitfallAlertStatus: PitfallAlertStatusResponse = {
  active: true,
  seeded_triads_count: 8,
  muted_sessions_count: 1,
};

export const mockDefaultAlertCard: PitfallAlertCardDTO = {
  alert_id: 'alert-mock-redis-01',
  subject: 'redis',
  intent_summary: '计划选择方案: [redis 分布式锁] (操作: 换成)',
  historical_pitfall: '业务偶发长尾 GC 导致锁过期被并发抢占，造成并发写脏数据与死锁雪崩故障',
  recommended_action: '使用 Redlock 看门狗自动续期机制，或切换至数据库行级乐观锁 CAS 结合本地排队',
  severity: 'critical',
  source_ref: '2025-04-12 生产故障复盘',
  drift_warning: '⚠️ 环境演进提示: 历史踩坑发生于 [Redis 6.2]，当前环境为 [Redis 7.2]，部分已知缺陷可能已被上游修复。',
  dispatch_channel: 'frontend_callout',
  is_muted: false,
};

export const mockEvaluationResponseCommitment: PitfallEvaluationResponse = {
  evaluation_id: 'eval-mock-001',
  intent_detected: true,
  intent_level: 'commitment',
  triad_matched: true,
  alert_generated: true,
  dispatched_channel: 'frontend_callout',
  latency_ms: 0.42,
  alert_card: mockDefaultAlertCard,
};

export const mockEvaluationResponseInquiry: PitfallEvaluationResponse = {
  evaluation_id: 'eval-mock-002',
  intent_detected: true,
  intent_level: 'inquiry',
  triad_matched: false,
  alert_generated: false,
  dispatched_channel: 'silent',
  latency_ms: 0.18,
  alert_card: null,
};

export const mockPredefinedQueries = [
  {
    label: '触发高危预警 (Redis 分布式锁)',
    query: '我们决定换成 redis 分布式锁来处理高并发扣库存',
  },
  {
    label: '触发中危预警 (MongoDB 单点写入)',
    query: '准备改用 mongodb 作为订单中心主存储',
  },
  {
    label: '日常探讨咨询 (静默放行 0 打扰)',
    query: '如何看待微服务架构下的分布式锁选型方案？',
  },
];
