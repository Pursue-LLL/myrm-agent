/**
 * [INPUT]
 * @/services/memory/businessTemplates
 *
 * [OUTPUT]
 * Fallback fixtures and simulation presets for Item 107:
 * BusinessScenarioExperienceTemplatesAndEscalationChecklistSuite.
 *
 * [POS]
 * Client layer offline simulation presets and test fixtures.
 * Single file < 150 lines. Strict typing, zero any.
 */

import type {
  BusinessExperienceTemplateDTO,
  EscalationEvaluationResponseDTO,
  RecordValidationResponseDTO,
} from '@/services/memory/businessTemplates';

export const FALLBACK_BUSINESS_ANALYSIS_TEMPLATE: BusinessExperienceTemplateDTO = {
  template_id: 'BA-REV-01',
  name: '经营分析与PPT复盘三方法经验模板',
  category: 'business_analysis',
  summary: '对标企业经营分析与PPT复盘场景的三类可复用方法：公式值回查、多源口径核对与交付前模板验收，复用检查方法而非历史旧数据。',
  checklist_steps: [
    {
      step_index: 1,
      name: '复杂表格公式计算值回查',
      description: '解析包含毛利率、环比增长等计算指标的复杂电子表格时，读取公式计算结果与缓存值，绝不可将原始公式字符串直接作为统计指标输出。',
      mandatory: true,
      validation_rule: 'cell_value != formula_raw_string and is_numeric(cell_value)',
    },
    {
      step_index: 2,
      name: '多源冲突数据口径显式核对',
      description: '当销售台账、财务系统与一线客户反馈之间存在统计口径偏差时，在结论中明确注明各源口径及对齐依据，禁止单方面静默覆盖任一权威数据源。',
      mandatory: true,
      validation_rule: 'source_attribution_declared and conflict_resolution_noted',
    },
    {
      step_index: 3,
      name: '交付前规范模板验收检查',
      description: '生成汇报图表与大纲前，核对数字可信度、结论逻辑链支撑以及格式规范，确保结论具备直接业务证据支持。',
      mandatory: true,
      validation_rule: 'verify_evidence_links and verify_chart_kpi_alignment',
    },
  ],
  boundary_conditions: [
    '复用排障检查方法，严格禁止复用上一周期的业务数字',
    '涉及跨表引用时必须进行完整性校验',
  ],
  sample_trajectory_ref: 'traj_ppt_review_margin_analysis',
  version: '1.1.0',
  tags: ['business_analysis', 'excel_formula', 'ppt_review', 'kpi_audit'],
  metadata: {
    domain: 'management_reporting',
    source: 'OpenViking_experience_benchmark',
  },
  validated_count: 12,
  rejected_count: 0,
  last_validated_at: '2026-10-08T05:00:00Z',
};

export const FALLBACK_RETAIL_EXCHANGE_TEMPLATE: BusinessExperienceTemplateDTO = {
  template_id: 'RET-EXC-01',
  name: '消费者售后换货全链路先问必查标准规程',
  category: 'retail_exchange',
  summary: '零售与电商客服售后换货标准化流程：强制执行“先问身份意图、必查状态政策库存、确认后办理、告知后续”闭环，杜绝顺序颠倒导致违反政策。',
  checklist_steps: [
    {
      step_index: 1,
      name: '先问: 身份、订单号与换货诉求',
      description: '核验用户身份与有效订单号，并明确顾客的具体换货诉求。',
      mandatory: true,
      validation_rule: 'identity_verified and order_id_present and intent_classified',
    },
    {
      step_index: 2,
      name: '必查: 物流履约状态、售后政策与目标库存',
      description: '强制校验原订单签收状态、保修窗口，以及目标更换SKU的当前实时库存。',
      mandatory: true,
      validation_rule: 'shipment_delivered and warranty_window_valid and target_sku_in_stock',
    },
    {
      step_index: 3,
      name: '显式确认: 换货明细与寄回协议',
      description: '向用户出示更换商品规格并获得显式确认后方可调用创建工具。',
      mandatory: true,
      validation_rule: 'user_explicitly_confirmed_exchange_spec',
    },
    {
      step_index: 4,
      name: '办理: 原子创建换货单与物流标签',
      description: '调用后台换货办理工具，原子生成换货服务单号与逆向物流运单。',
      mandatory: true,
      validation_rule: 'exchange_order_created and rma_label_generated',
    },
    {
      step_index: 5,
      name: '告知后续: 退货指引与新包裹时效',
      description: '向用户传达退货包裹寄回指引、质检时效以及新包裹的预计到达时间。',
      mandatory: true,
      validation_rule: 'return_instructions_dispatched and eta_timeline_communicated',
    },
  ],
  boundary_conditions: [
    '严禁在未校验库存情况下承诺换新',
    '严禁在用户未确认前调用 commit_exchange 工具',
  ],
  sample_trajectory_ref: 'traj_tau2_retail_exchange_clean',
  version: '1.2.0',
  tags: ['retail', 'customer_service', 'exchange', 'tau2_benchmark'],
  metadata: {
    domain: 'e_commerce_service',
    source: 'tau2_retail_exchange_matrix',
  },
  validated_count: 28,
  rejected_count: 1,
  last_validated_at: '2026-10-08T05:20:00Z',
};

export const FALLBACK_ESCALATION_GATE_TEMPLATE: BusinessExperienceTemplateDTO = {
  template_id: 'ESC-GATE-01',
  name: '售后与异常处置例外转人工决策门禁',
  category: 'escalation_gate',
  summary: '针对政策模糊、目标商品断码缺货、用户争议纠偏或情绪升级场景，实施确定性转人工拦截并生成交接单。',
  checklist_steps: [
    {
      step_index: 1,
      name: '政策模糊与定制例外扫描',
      description: '涉及定制商品或政策条款存在冲突解释时，立即挂起并触发例外转人工。',
      mandatory: true,
      validation_rule: 'policy_ambiguity_flag == True or is_custom_order == True',
    },
    {
      step_index: 2,
      name: '目标更换SKU缺货断码检查',
      description: '目标更换款式缺货时，禁止虚假承诺，直接引导转人工客服协商方案。',
      mandatory: true,
      validation_rule: 'sku_inventory <= 0',
    },
    {
      step_index: 3,
      name: '用户纠错争议与情绪升级熔断',
      description: '连续两次纠正 Agent 结论或情绪强烈时，立即熔断自动化处理并转人工。',
      mandatory: true,
      validation_rule: 'user_dispute_count >= 2 or sentiment_escalated == True',
    },
    {
      step_index: 4,
      name: '结构化人工交接包组装',
      description: '将身份、订单、诉求、缺货事实与排查日志格式化打包交接给人工客服。',
      mandatory: true,
      validation_rule: 'generate_human_handover_package',
    },
  ],
  boundary_conditions: [
    '转人工后 Agent 自动切为只读辅助模式',
    '必须完整保留上下文证据链',
  ],
  sample_trajectory_ref: 'traj_escalation_out_of_stock_dispute',
  version: '1.0.0',
  tags: ['escalation', 'safety_gate', 'human_in_the_loop', 'sentiment_guard'],
  metadata: {
    domain: 'governance_and_safety',
    source: 'OpenViking_escalation_protocol',
  },
  validated_count: 19,
  rejected_count: 0,
  last_validated_at: '2026-10-08T05:30:00Z',
};

export const FALLBACK_TEMPLATES_LIST: BusinessExperienceTemplateDTO[] = [
  FALLBACK_BUSINESS_ANALYSIS_TEMPLATE,
  FALLBACK_RETAIL_EXCHANGE_TEMPLATE,
  FALLBACK_ESCALATION_GATE_TEMPLATE,
];

export const FALLBACK_ESCALATION_EVALUATION_RESPONSE: EscalationEvaluationResponseDTO = {
  action: 'escalate_to_human',
  reason: 'policy_ambiguity',
  message: '订单涉及特殊定制品类或退换货政策存在歧义条款，已阻断自主办理并触发人工客服审核。',
  required_context: {
    order_id: 'ORD-DEMO-001',
    user_id: 'USR-8821',
    intent: '换货',
    shipment_status: 'delivered',
    policy_issue: 'custom_order',
  },
  suggested_skill_or_tool: 'route_to_human_specialist',
};

export const FALLBACK_VALIDATION_RECORD_RESPONSE: RecordValidationResponseDTO = {
  status: 'ok',
  record_id: 'val_sim_01',
  template_id: 'RET-EXC-01',
  is_validated: true,
  validated_count: 29,
  rejected_count: 1,
  timestamp: '2026-10-08T05:45:00Z',
};
