import { apiRequest } from '@/lib/api';
import { approveSkillDraft, rejectSkillDraft } from '@/services/skill';

export type SkillGrowthStatus =
  | 'PENDING_REVIEW'
  | 'AUTO_APPLIED'
  | 'FAILED_SCAN'
  | 'BLOCKED_LOCKED'
  | 'APPROVED'
  | 'REJECTED'
  | 'APPLY_FAILED';

export type SkillGrowthSource = 'draft' | 'evolution';

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
  const response = await apiRequest<SkillGrowthCaseDetailApiItem>(
    `/skill-growth/cases/${encodeURIComponent(caseId)}`,
  );
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

export async function rejectSkillGrowthCase(item: SkillGrowthCaseSummary, reason?: string): Promise<SkillGrowthActionResult> {
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
