export type ReviewerRole = 'reviewer_a_intent' | 'reviewer_b_blind';

export type FindingSeverity = 'critical' | 'major' | 'minor' | 'info';

export type FindingCategory =
  | 'intent_drift'
  | 'missing_requirement'
  | 'over_engineering'
  | 'type_safety'
  | 'boundary_edge_case'
  | 'regression_risk';

export type ArbiterDecision = 'admitted' | 'blocked' | 'needs_revision';

export interface ReviewFinding {
  finding_id: string;
  reviewer_role: ReviewerRole;
  file_path: string;
  line_range: [number, number];
  severity: FindingSeverity;
  category: FindingCategory;
  title: string;
  description: string;
  suggested_action: string;
}

export interface ReviewerReport {
  reviewer_id: string;
  perspective: 'intent_alignment' | 'blind_clean_context';
  passed: boolean;
  findings: ReviewFinding[];
  summary: string;
  is_clean_context: boolean;
}

export interface ArbiterVerdict {
  session_id: string;
  decision: ArbiterDecision;
  total_findings_count: number;
  critical_count: number;
  major_count: number;
  minor_count: number;
  blocker_reasons: string[];
  deduplicated_findings: ReviewFinding[];
  auto_fix_prompts: string[];
  reviewer_a_summary: string;
  reviewer_b_summary: string;
}

export const INITIAL_MOCK_REVIEWER_A: ReviewerReport = {
  reviewer_id: 'reviewer-a-intent-gate',
  perspective: 'intent_alignment',
  passed: true,
  findings: [],
  summary: 'Reviewer A: 完全对齐任务原始要求，无目标漂移，核心功能点 100% 覆盖。',
  is_clean_context: false,
};

export const INITIAL_MOCK_REVIEWER_B: ReviewerReport = {
  reviewer_id: 'reviewer-b-blind-gate',
  perspective: 'blind_clean_context',
  passed: true,
  findings: [],
  summary: 'Reviewer B (盲态全新子代理): 独立上下文检查通过，无 Any 类型隐患，边界防护稳健。',
  is_clean_context: true,
};

export const INITIAL_MOCK_ARBITER_VERDICT: ArbiterVerdict = {
  session_id: 'session-review-demo-001',
  decision: 'admitted',
  total_findings_count: 0,
  critical_count: 0,
  major_count: 0,
  minor_count: 0,
  blocker_reasons: [],
  deduplicated_findings: [],
  auto_fix_prompts: [],
  reviewer_a_summary: '意图对齐良好，无需求遗漏。',
  reviewer_b_summary: '盲态客观检验通过，零类型逃逸，零破坏性变更。',
};
