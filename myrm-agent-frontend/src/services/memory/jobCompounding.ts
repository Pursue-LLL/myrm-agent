/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: Frontend API client transport)
 *
 * [OUTPUT]
 * Domain-Specific Agent Job Description & Preference Compounding DTOs & API clients:
 * - saveJobDescription, getJobDescription (Pillar 1-4 job description builder)
 * - checkApprovalBoundary (Pillar 4 autonomous vs approval fence evaluation)
 * - recordCompoundedRule, listCompoundedRules (Positive preferences, negative constraints, troubleshooting lessons)
 * - evaluateMaturity (Rookie -> Practitioner -> Specialist -> Partner maturity metrics)
 *
 * [POS]
 * Frontend API service for Topic 01 Item 90 (xAI Grok Bot Bluebook-inspired Domain Job Description
 * and progressive lesson compounding suite).
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface ApprovalBoundaryDTO {
  autonomous_actions: string[];
  requires_approval_actions: string[];
}

export interface JobDescriptionSpecDTO {
  agent_id: string;
  job_title: string;
  target_scope: string;
  tools_and_sources: string[];
  work_style: string;
  approval_boundary: ApprovalBoundaryDTO;
  created_at: string;
  updated_at: string;
}

export interface SaveJobDescriptionRequestDTO {
  agent_id: string;
  job_title: string;
  target_scope: string;
  tools_and_sources?: string[];
  work_style?: string;
  autonomous_actions?: string[];
  requires_approval_actions?: string[];
}

export type CompoundedRuleType = 'positive_preference' | 'negative_constraint' | 'inspection_lesson';

export interface CompoundedRuleDTO {
  rule_id: string;
  agent_id: string;
  rule_type: CompoundedRuleType | string;
  statement: string;
  trigger_condition: string;
  evidence_source: string;
  hit_count: number;
  created_at: string;
}

export interface RecordRuleRequestDTO {
  agent_id: string;
  rule_type?: CompoundedRuleType | string;
  statement: string;
  trigger_condition: string;
  evidence_source: string;
}

export interface CheckApprovalRequestDTO {
  agent_id: string;
  action_name: string;
}

export interface CheckApprovalResponseDTO {
  agent_id: string;
  action_name: string;
  needs_approval: boolean;
  reason: string;
}

export type MaturityTier = 'rookie' | 'practitioner' | 'specialist' | 'partner';

export interface CompoundingMaturityReportDTO {
  agent_id: string;
  job_title: string;
  total_rules_count: number;
  positive_preferences_count: number;
  negative_constraints_count: number;
  inspection_lessons_count: number;
  maturity_score: number;
  tier: MaturityTier | string;
  summary: string;
}

/**
 * Creates or updates an agent's 4-pillar job description.
 */
export async function saveJobDescription(
  request: SaveJobDescriptionRequestDTO
): Promise<JobDescriptionSpecDTO> {
  return apiRequest<JobDescriptionSpecDTO>('/memory/job-compounding/jobs', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Retrieves the 4-pillar job description for an agent.
 */
export async function getJobDescription(
  agentId: string
): Promise<JobDescriptionSpecDTO> {
  return apiRequest<JobDescriptionSpecDTO>(
    `/memory/job-compounding/jobs/${encodeURIComponent(agentId)}`
  );
}

/**
 * Evaluates whether an upcoming action requires human escalation.
 */
export async function checkApprovalBoundary(
  request: CheckApprovalRequestDTO
): Promise<CheckApprovalResponseDTO> {
  return apiRequest<CheckApprovalResponseDTO>('/memory/job-compounding/approval/check', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Appends a new compounded domain rule from feedback.
 */
export async function recordCompoundedRule(
  request: RecordRuleRequestDTO
): Promise<CompoundedRuleDTO> {
  return apiRequest<CompoundedRuleDTO>('/memory/job-compounding/rules', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Lists all compounded rules accumulated by an agent.
 */
export async function listCompoundedRules(
  agentId: string,
  ruleType?: string
): Promise<CompoundedRuleDTO[]> {
  const query = ruleType ? `?rule_type=${encodeURIComponent(ruleType)}` : '';
  return apiRequest<CompoundedRuleDTO[]>(
    `/memory/job-compounding/rules/${encodeURIComponent(agentId)}${query}`
  );
}

/**
 * Evaluates compounding growth maturity score, tier and statistics.
 */
export async function evaluateMaturity(
  agentId: string
): Promise<CompoundingMaturityReportDTO> {
  return apiRequest<CompoundingMaturityReportDTO>(
    `/memory/job-compounding/maturity/${encodeURIComponent(agentId)}`
  );
}
