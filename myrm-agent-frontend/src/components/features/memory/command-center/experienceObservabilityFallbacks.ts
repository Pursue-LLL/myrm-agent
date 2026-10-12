/**
 * [INPUT]
 * @/services/memory/experienceObservability
 *
 * [OUTPUT]
 * Fallback fixtures and simulation presets for Item 108:
 * ZeroRefactorHostLifecyclePluginAndExperienceObservabilitySuite.
 *
 * [POS]
 * Client layer offline simulation presets and test fixtures.
 * Single file < 200 lines. Strict typing, zero any.
 */

import type {
  ExperienceObservabilityMetricDTO,
  HostPluginConfigDTO,
  ObservabilityDashboardResponseDTO,
  SessionTraceEvidenceDTO,
} from '@/services/memory/experienceObservability';

export const FALLBACK_OBSERVABILITY_METRICS: ExperienceObservabilityMetricDTO[] = [
  {
    entry_id: 'proc_git_push_safe',
    name: 'SafeGitBranchPushGuard',
    source_session_id: 'sess_release_incident_09',
    access_channel: 'plugin',
    recall_count: 142,
    injection_count: 88,
    success_count: 85,
    dispute_count: 3,
    success_rate: 0.966,
    effect_status: 'effective',
    last_observed_at: '2026-10-08T06:00:00Z',
  },
  {
    entry_id: 'proc_db_index_ddl',
    name: 'ConcurrentDbIndexMigrationGuard',
    source_session_id: 'sess_postgres_lock_timeout_42',
    access_channel: 'mcp',
    recall_count: 57,
    injection_count: 34,
    success_count: 32,
    dispute_count: 2,
    success_rate: 0.941,
    effect_status: 'effective',
    last_observed_at: '2026-10-08T05:55:00Z',
  },
  {
    entry_id: 'BA-REV-01',
    name: '经营分析与PPT复盘三方法经验模板',
    source_session_id: 'sess_ppt_margin_analysis_88',
    access_channel: 'skill',
    recall_count: 43,
    injection_count: 29,
    success_count: 27,
    dispute_count: 2,
    success_rate: 0.931,
    effect_status: 'effective',
    last_observed_at: '2026-10-08T05:50:00Z',
  },
  {
    entry_id: 'RET-EXC-01',
    name: '消费者售后换货全链路先问必查标准规程',
    source_session_id: 'sess_tau2_retail_exchange_01',
    access_channel: 'plugin',
    recall_count: 98,
    injection_count: 74,
    success_count: 69,
    dispute_count: 5,
    success_rate: 0.932,
    effect_status: 'effective',
    last_observed_at: '2026-10-08T05:40:00Z',
  },
  {
    entry_id: 'ESC-GATE-01',
    name: '售后与异常处置例外转人工决策门禁',
    source_session_id: 'sess_out_of_stock_dispute_12',
    access_channel: 'plugin',
    recall_count: 61,
    injection_count: 45,
    success_count: 44,
    dispute_count: 1,
    success_rate: 0.978,
    effect_status: 'effective',
    last_observed_at: '2026-10-08T05:30:00Z',
  },
];

export const FALLBACK_SESSION_TRACES: Record<string, SessionTraceEvidenceDTO> = {
  sess_release_incident_09: {
    session_id: 'sess_release_incident_09',
    title: 'Git生产分支误删与保护规程复盘会话',
    trajectory_summary:
      '生产发版中工程师误执行了带强制选项的推送，后经回滚分析提炼出预检三步法。',
    key_evidence_snippets: [
      '[Turn 4] User: 别强制推送，先检查目标远程分支保护规则！',
      '[Turn 5] Agent: 执行 git status 确认本地工作区干净，校验上游 hash 一致性。',
    ],
    agent_role: 'DevOpsEngineer',
    timestamp: '2026-09-18T10:00:00Z',
  },
  sess_postgres_lock_timeout_42: {
    session_id: 'sess_postgres_lock_timeout_42',
    title: 'PostgreSQL千万行大表添加索引死锁排障',
    trajectory_summary:
      '高并发库上直跑 CREATE INDEX 导致排他锁阻塞业务连接，提炼出 CONCURRENTLY 规约。',
    key_evidence_snippets: [
      '[Turn 2] Error: lock timeout during CREATE INDEX ON orders(user_id)',
      '[Turn 3] Agent: 切换为 CREATE INDEX CONCURRENTLY 并关闭单事务块包裹。',
    ],
    agent_role: 'DatabaseArchitect',
    timestamp: '2026-09-20T14:30:00Z',
  },
  sess_ppt_margin_analysis_88: {
    session_id: 'sess_ppt_margin_analysis_88',
    title: 'Q3季度毛利率跨表公式提取复盘会话',
    trajectory_summary:
      '电子表格中的毛利率公式未取计算值导致大纲数据偏差，总结出公式值回查与模板验收方法。',
    key_evidence_snippets: [
      '[Turn 6] User: 为什么汇报大纲里毛利率写的是 "=C2/B2" 字符串？',
      '[Turn 7] Agent: 修正提取器读取 openpyxl data_only 计算结果值，完成对齐。',
    ],
    agent_role: 'BusinessAnalyst',
    timestamp: '2026-09-22T08:15:00Z',
  },
  sess_tau2_retail_exchange_01: {
    session_id: 'sess_tau2_retail_exchange_01',
    title: 'τ²-bench 消费者售后换货标准履约会话',
    trajectory_summary:
      '顾客要求更换服装尺码，严格执行核验身份、校验签收、确认库存后办理，未产生越权违规。',
    key_evidence_snippets: [
      '[Turn 1] User: 我的外套尺码小了想换大一号。',
      '[Turn 2] Agent: 已核验订单并查询目标黑色L码实时库存剩余 12 件，请确认寄回旧件。',
    ],
    agent_role: 'CustomerServiceRepresentative',
    timestamp: '2026-09-25T11:45:00Z',
  },
  sess_out_of_stock_dispute_12: {
    session_id: 'sess_out_of_stock_dispute_12',
    title: '换货目标SKU断码缺货触发转人工门禁会话',
    trajectory_summary:
      '顾客诉求更换的款式全网断码，Agent 阻断盲目承诺发货并格式化输出人工交接工单。',
    key_evidence_snippets: [
      '[Turn 3] Agent: 查询发现该款式已全量售罄，根据政策门禁为您接入高级人工客服专员协商补偿券。',
    ],
    agent_role: 'CustomerServiceRepresentative',
    timestamp: '2026-09-26T16:20:00Z',
  },
};

export const FALLBACK_HOST_PLUGIN_CONFIG: HostPluginConfigDTO = {
  enabled: true,
  active_channel: 'plugin',
  auto_warmup: true,
  auto_capture: true,
  auto_commit: true,
  monitored_host: 'claude_code',
};

export const FALLBACK_DASHBOARD_RESPONSE: ObservabilityDashboardResponseDTO = {
  status: 'ok',
  total_experiences_tracked: 5,
  overall_success_rate: 0.95,
  total_recalls: 401,
  total_injections: 270,
  plugin_config: FALLBACK_HOST_PLUGIN_CONFIG,
  metrics: FALLBACK_OBSERVABILITY_METRICS,
};
