/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 * ./core::approveSkillDraft,rejectSkillDraft (POS: 技能审批 API)
 *
 * [OUTPUT]
 * SkillGrowthCase/Summary/Audit DTO 与 `/skill-growth/*` cases/detail/stats/audit API。
 *
 * [POS]
 * 技能进化（growth）客户端。`/skill-growth/*` REST 契约。
 */

import { apiRequest } from '@/lib/api';
import { approveSkillDraft, rejectSkillDraft } from './core';

export type SkillGrowthStatus =
  'PENDING_REVIEW' | 'AUTO_APPLIED' | 'FAILED_SCAN' | 'BLOCKED_LOCKED' | 'APPROVED' | 'REJECTED' | 'APPLY_FAILED';

export type SkillGrowthSource = 'draft' | 'evolution' | 'continual';

export interface RuntimeFailureEvidence {
  source: string;
  tool_name: string;
  error_signature: string;
  tool_args_hash: string | null;
  loop_kind: string | null;
  skill_version: string | null;
  attribution_confidence: number;
  failure_count: number;
  first_seen_at: string;
  last_seen_at: string;
  candidate_skill_names: string[];
}

export interface VerificationProofDto {
  is_verified: boolean;
  hollow_detected: boolean;
  success_streak: number;
  blast_radius?: { files: number; lines: number };
  verification_summary?: string;
  command_results?: Array<{ command?: string; success?: boolean; stdout?: string; stderr?: string }>;
  verified_at?: string;
}

export interface MetricPredictionDto {
  metric_name: string;
  direction: 'INCREASE' | 'DECREASE' | 'NEUTRAL';
  baseline_value: number;
  target_value: number;
  rationale: string;
}

export interface PredictionManifestDto {
  manifest_id: string;
  change_id: string;
  created_at: string;
  predictions: MetricPredictionDto[];
  falsification_conditions: string[];
  verdict?: string | null;
  pareto_generalization_verdict?: string | null;
  search_pass_rate?: number | null;
  test_pass_rate?: number | null;
}

export interface AttributionResultDto {
  manifest_id: string;
  verdict: 'CONFIRMED' | 'REFUTED' | 'REGRESSION' | 'INCONCLUSIVE';
  attributed_at: string;
  metric_deltas: Record<string, number>;
  unpredicted_regressions: string[];
  details: string;
}

export interface ProxyAlignmentDto {
  contract_id: string;
  verdict: 'aligned' | 'accepted_tradeoff' | 'goodhart_drift' | 'unconverged';
  sample_size: number;
  intent_delta: number;
  proxy_improvement: number;
  flagged_proxies: string[];
  warning_message: string;
}

interface SkillGrowthCaseSummaryApiItem {
  id: string;
  source: SkillGrowthSource;
  status: SkillGrowthStatus;
  skill_name: string;
  skill_id: string | null;
  growth_type: string;
  title: string;
  summary: string;
  description: string | null;
  confidence: number | null;
  test_passed: boolean | null;
  apply_status: string | null;
  apply_error: string | null;
  reason_code: string | null;
  remediation: string | null;
  runtime_failure: RuntimeFailureEvidence | null;
  chat_id: string | null;
  form_metadata: { schedule_hint?: string; form_reasoning?: string } | null;
  has_diff: boolean;
  has_trajectory: boolean;
  has_trigger_condition: boolean;
  has_skill_steps: boolean;
  created_at: string;
  impacted_dependents: string[];
  verification_proof?: VerificationProofDto | null;
  target_layer?: string | null;
  target_pathology?: string | null;
  prediction_manifest?: PredictionManifestDto | null;
  attribution_result?: AttributionResultDto | null;
  proxy_alignment?: ProxyAlignmentDto | null;
}

interface SkillGrowthCaseDetailApiItem extends SkillGrowthCaseSummaryApiItem {
  trigger_condition: string | null;
  skill_steps: string | null;
  original_content: string | null;
  proposed_content: string | null;
  trajectory: string | null;
}

interface SkillGrowthCaseApiResponse {
  items: SkillGrowthCaseSummaryApiItem[];
  total: number;
}

interface SkillGrowthStatsApiResponse {
  total: number;
  pending_review: number;
  auto_applied: number;
  blocked: number;
}

interface SkillGrowthAuditApiItem {
  event_id: string;
  case_id: string;
  source: SkillGrowthSource;
  status: SkillGrowthStatus;
  skill_name: string;
  skill_id: string | null;
  growth_type: string;
  reason: string;
  confidence: number | null;
  severity: string | null;
  reason_code: string | null;
  remediation: string | null;
  created_at: string;
}

interface SkillGrowthAuditApiResponse {
  items: SkillGrowthAuditApiItem[];
  total: number;
}

interface SkillGrowthAuditBucketApiItem {
  key: string;
  count: number;
  percentage: number;
}

interface SkillGrowthAuditSkillBucketApiItem {
  skill_name: string;
  skill_id: string | null;
  count: number;
  percentage: number;
}

interface SkillGrowthAuditStatsApiResponse {
  total_events: number;
  avg_confidence: number;
  by_status: SkillGrowthAuditBucketApiItem[];
  top_skills: SkillGrowthAuditSkillBucketApiItem[];
  time_range_days: number;
}

export interface SkillGrowthCaseSummary {
  id: string;
  source: SkillGrowthSource;
  status: SkillGrowthStatus;
  skillName: string;
  skillId: string | null;
  growthType: string;
  title: string;
  summary: string;
  description: string | null;
  confidence: number | null;
  testPassed: boolean | null;
  applyStatus: string | null;
  applyError: string | null;
  reasonCode: string | null;
  remediation: string | null;
  runtimeFailure: RuntimeFailureEvidence | null;
  chatId: string | null;
  formMetadata: { scheduleHint?: string; formReasoning?: string } | null;
  hasDiff: boolean;
  hasTrajectory: boolean;
  hasTriggerCondition: boolean;
  hasSkillSteps: boolean;
  createdAt: string;
  impactedDependents: string[];
  verificationProof: VerificationProofDto | null;
  targetLayer?: string | null;
  targetPathology?: string | null;
  predictionManifest?: PredictionManifestDto | null;
  attributionResult?: AttributionResultDto | null;
  proxyAlignment?: ProxyAlignmentDto | null;
}

export interface SkillGrowthCaseDetail extends SkillGrowthCaseSummary {
  triggerCondition: string | null;
  skillSteps: string | null;
  originalContent: string | null;
  proposedContent: string | null;
  trajectory: string | null;
}

/** @deprecated Use SkillGrowthCaseSummary for lists; detail fields load on demand. */
export type SkillGrowthCase = SkillGrowthCaseDetail;

export interface SkillGrowthSummary {
  total: number;
  pendingReview: number;
  autoApplied: number;
  blocked: number;
}

export interface SkillGrowthAuditEntry {
  eventId: string;
  caseId: string;
  source: SkillGrowthSource;
  status: SkillGrowthStatus;
  skillName: string;
  skillId: string | null;
  growthType: string;
  reason: string;
  confidence: number | null;
  severity: string | null;
  reasonCode: string | null;
  remediation: string | null;
  createdAt: string;
}

export interface SkillGrowthActionResult {
  status: string;
  skill_id?: string | null;
  apply_status?: string | null;
  apply_error?: string | null;
  remediation?: string | null;
}

export interface SkillGrowthAuditBucket {
  key: string;
  count: number;
  percentage: number;
}

export interface SkillGrowthAuditSkillBucket {
  skillName: string;
  skillId: string | null;
  count: number;
  percentage: number;
}

export interface SkillGrowthAuditStats {
  totalEvents: number;
  avgConfidence: number;
  byStatus: SkillGrowthAuditBucket[];
  topSkills: SkillGrowthAuditSkillBucket[];
  timeRangeDays: number;
}

function mapSummary(item: SkillGrowthCaseSummaryApiItem): SkillGrowthCaseSummary {
  return {
    id: item.id,
    source: item.source,
    status: item.status,
    skillName: item.skill_name,
    skillId: item.skill_id,
    growthType: item.growth_type,
    title: item.title,
    summary: item.summary,
    description: item.description,
    confidence: item.confidence,
    testPassed: item.test_passed,
    applyStatus: item.apply_status,
    applyError: item.apply_error,
    reasonCode: item.reason_code,
    remediation: item.remediation,
    runtimeFailure: item.runtime_failure,
    chatId: item.chat_id,
    formMetadata: item.form_metadata
      ? { scheduleHint: item.form_metadata.schedule_hint, formReasoning: item.form_metadata.form_reasoning }
      : null,
    hasDiff: item.has_diff,
    hasTrajectory: item.has_trajectory,
    hasTriggerCondition: item.has_trigger_condition,
    hasSkillSteps: item.has_skill_steps,
    createdAt: item.created_at,
    impactedDependents: item.impacted_dependents ?? [],
    verificationProof: item.verification_proof ?? null,
    targetLayer: item.target_layer ?? null,
    targetPathology: item.target_pathology ?? null,
    predictionManifest: item.prediction_manifest ?? null,
    attributionResult: item.attribution_result ?? null,
    proxyAlignment: item.proxy_alignment ?? null,
  };
}

function mapDetail(item: SkillGrowthCaseDetailApiItem): SkillGrowthCaseDetail {
  return {
    ...mapSummary(item),
    triggerCondition: item.trigger_condition,
    skillSteps: item.skill_steps,
    originalContent: item.original_content,
    proposedContent: item.proposed_content,
    trajectory: item.trajectory,
  };
}

function mapAuditEntry(item: SkillGrowthAuditApiItem): SkillGrowthAuditEntry {
  return {
    eventId: item.event_id,
    caseId: item.case_id,
    source: item.source,
    status: item.status,
    skillName: item.skill_name,
    skillId: item.skill_id,
    growthType: item.growth_type,
    reason: item.reason,
    confidence: item.confidence,
    severity: item.severity,
    reasonCode: item.reason_code,
    remediation: item.remediation,
    createdAt: item.created_at,
  };
}

function sortByCreatedAtDesc<T extends { createdAt: string }>(items: T[]): T[] {
  return [...items].sort((left, right) => {
    return new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime();
  });
}

export interface SkillGrowthCaseListResult {
  items: SkillGrowthCaseSummary[];
  total: number;
}

export async function listSkillGrowthCases(limit: number = 50): Promise<SkillGrowthCaseListResult> {
  const response = await apiRequest<SkillGrowthCaseApiResponse>(`/skill-growth/cases?limit=${limit}`);
  return {
    items: sortByCreatedAtDesc(response.items.map(mapSummary)),
    total: response.total,
  };
}

export async function getSkillGrowthCaseDetail(caseId: string): Promise<SkillGrowthCaseDetail> {
  const response = await apiRequest<SkillGrowthCaseDetailApiItem>(`/skill-growth/cases/${encodeURIComponent(caseId)}`);
  return mapDetail(response);
}

export async function getSkillGrowthSummary(): Promise<SkillGrowthSummary> {
  const response = await apiRequest<SkillGrowthStatsApiResponse>('/skill-growth/stats');
  return {
    total: response.total,
    pendingReview: response.pending_review,
    autoApplied: response.auto_applied,
    blocked: response.blocked,
  };
}

export async function approveSkillGrowthCase(
  item: SkillGrowthCaseSummary,
  applyMode: 'immediate' | 'shadow' = 'immediate',
): Promise<SkillGrowthActionResult> {
  if (item.source === 'draft') {
    const draftId = item.id.replace('draft:', '');
    const response = await approveSkillDraft(draftId, item.skillName);
    return {
      status: response.status,
      skill_id: null,
      apply_status: response.materialized === false ? 'FAILED' : 'APPLIED',
      apply_error: response.error ?? null,
      remediation: response.error ?? null,
    };
  }

  const evolutionId = item.id.replace('evolution:', '');
  return apiRequest<SkillGrowthActionResult>(`/evolution/pending/${evolutionId}/approve`, {
    method: 'POST',
    body: JSON.stringify({ apply_mode: applyMode }),
  });
}

export async function rejectSkillGrowthCase(
  item: SkillGrowthCaseSummary,
  reason?: string,
): Promise<SkillGrowthActionResult> {
  if (item.source === 'draft') {
    const draftId = item.id.replace('draft:', '');
    const response = await rejectSkillDraft(draftId);
    return { status: response.status, apply_status: null, remediation: null };
  }

  const evolutionId = item.id.replace('evolution:', '');
  return apiRequest<SkillGrowthActionResult>(`/evolution/pending/${evolutionId}/reject`, {
    method: 'POST',
    body: JSON.stringify({ reason: reason ?? null }),
  });
}

export interface SkillGrowthReviseResult {
  status: string;
  skill_id: string | null;
  test_passed: boolean;
  reason_code: string | null;
  remediation: string | null;
}

export async function reviseSkillGrowthCase(
  item: SkillGrowthCaseSummary,
  evolvedContent: string,
): Promise<SkillGrowthReviseResult> {
  const evolutionId = item.id.replace('evolution:', '');
  return apiRequest<SkillGrowthReviseResult>(`/evolution/pending/${evolutionId}/revise`, {
    method: 'PATCH',
    body: JSON.stringify({ evolved_content: evolvedContent }),
  });
}

export async function listSkillGrowthAudit(limit: number = 20, days: number = 30): Promise<SkillGrowthAuditEntry[]> {
  const response = await apiRequest<SkillGrowthAuditApiResponse>(`/skill-growth/audit?limit=${limit}&days=${days}`);
  return response.items.map(mapAuditEntry);
}

export async function getSkillGrowthAuditStats(timeRangeDays: number): Promise<SkillGrowthAuditStats> {
  const response = await apiRequest<SkillGrowthAuditStatsApiResponse>(
    `/skill-growth/audit/stats?time_range_days=${timeRangeDays}`,
  );
  return {
    totalEvents: response.total_events,
    avgConfidence: response.avg_confidence,
    byStatus: response.by_status.map((item) => ({
      key: item.key,
      count: item.count,
      percentage: item.percentage,
    })),
    topSkills: response.top_skills.map((item) => ({
      skillName: item.skill_name,
      skillId: item.skill_id,
      count: item.count,
      percentage: item.percentage,
    })),
    timeRangeDays: response.time_range_days,
  };
}

export interface MetricPredictionRequest {
  metric_name: string;
  direction: 'increase' | 'decrease' | 'neutral' | 'preserve_min';
  baseline_value: number;
  target_value: number;
  tolerance?: number;
}

export interface EvaluatePredictionManifestRequest {
  manifest_id: string;
  target_component: string;
  rationale: string;
  predictions: MetricPredictionRequest[];
  actual_metrics: Record<string, number>;
  rollback_patch?: string | null;
}

export interface MetricAttributionDetailResponse {
  metric_name: string;
  predicted_target: number;
  actual_value: number;
  delta: number;
  verdict: 'confirmed' | 'refuted' | 'regression' | 'inconclusive';
  explanation: string;
}

export interface ManifestAttributionResultResponse {
  manifest_id: string;
  overall_verdict: 'confirmed' | 'refuted' | 'regression' | 'inconclusive';
  metric_attributions: MetricAttributionDetailResponse[];
  confidence_score: number;
  recommended_action: 'keep' | 'rollback' | 're_evaluate';
}

export async function evaluateManifestAttribution(
  payload: EvaluatePredictionManifestRequest,
): Promise<ManifestAttributionResultResponse> {
  const response = await apiRequest<{ data: ManifestAttributionResultResponse } | ManifestAttributionResultResponse>(
    '/skill-growth/manifest-attribution',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
  return 'data' in response ? (response as { data: ManifestAttributionResultResponse }).data : response;
}
