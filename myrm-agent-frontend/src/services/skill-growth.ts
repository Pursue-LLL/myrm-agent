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

interface SkillGrowthCaseApiItem {
  id: string;
  source: SkillGrowthSource;
  status: SkillGrowthStatus;
  skill_name: string;
  skill_id: string | null;
  growth_type: string;
  title: string;
  summary: string;
  description: string | null;
  trigger_condition: string | null;
  skill_steps: string | null;
  original_content: string | null;
  proposed_content: string | null;
  confidence: number | null;
  test_passed: boolean | null;
  apply_status: string | null;
  apply_error: string | null;
  reason_code: string | null;
  remediation: string | null;
  runtime_failure: RuntimeFailureEvidence | null;
  trajectory: string | null;
  created_at: string;
}

interface SkillGrowthCaseApiResponse {
  items: SkillGrowthCaseApiItem[];
  total: number;
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

export interface SkillGrowthCase {
  id: string;
  source: SkillGrowthSource;
  status: SkillGrowthStatus;
  skillName: string;
  skillId: string | null;
  growthType: string;
  title: string;
  summary: string;
  description: string | null;
  triggerCondition: string | null;
  skillSteps: string | null;
  originalContent: string | null;
  proposedContent: string | null;
  confidence: number | null;
  testPassed: boolean | null;
  applyStatus: string | null;
  applyError: string | null;
  reasonCode: string | null;
  remediation: string | null;
  runtimeFailure: RuntimeFailureEvidence | null;
  trajectory: string | null;
  createdAt: string;
}

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

function mapCase(item: SkillGrowthCaseApiItem): SkillGrowthCase {
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
    triggerCondition: item.trigger_condition,
    skillSteps: item.skill_steps,
    originalContent: item.original_content,
    proposedContent: item.proposed_content,
    confidence: item.confidence,
    testPassed: item.test_passed,
    applyStatus: item.apply_status,
    applyError: item.apply_error,
    reasonCode: item.reason_code,
    remediation: item.remediation,
    runtimeFailure: item.runtime_failure,
    trajectory: item.trajectory,
    createdAt: item.created_at,
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

export async function listSkillGrowthCases(limit: number = 50): Promise<SkillGrowthCase[]> {
  const response = await apiRequest<SkillGrowthCaseApiResponse>(`/skill-growth/cases?limit=${limit}`);
  return sortByCreatedAtDesc(response.items.map(mapCase));
}

export async function getSkillGrowthSummary(limit: number = 50): Promise<SkillGrowthSummary> {
  const cases = await listSkillGrowthCases(limit);
  return {
    total: cases.length,
    pendingReview: cases.filter((item) => item.status === 'PENDING_REVIEW' || item.status === 'APPLY_FAILED').length,
    autoApplied: cases.filter((item) => item.status === 'AUTO_APPLIED').length,
    blocked: cases.filter((item) => item.status === 'BLOCKED_LOCKED' || item.status === 'FAILED_SCAN').length,
  };
}

export async function approveSkillGrowthCase(
  item: SkillGrowthCase,
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

export async function rejectSkillGrowthCase(item: SkillGrowthCase, reason?: string): Promise<SkillGrowthActionResult> {
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
