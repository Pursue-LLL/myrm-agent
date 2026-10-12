/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API client transport)
 *
 * [OUTPUT]
 * Task Triad Trajectory and Anti-Loop Execution Blackbox DTOs & API clients:
 * - recordMilestone
 * - recordFailedAttempt
 * - recordUserSteering
 * - checkActionProhibited
 * - getAntiLoopSnapshot
 * - getTaskBlackbox
 *
 * [POS]
 * Frontend API service for GPT-6 Astra-inspired task triad state management (Topic 01 Item 86).
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface MilestoneItemDTO {
  milestone_id: string;
  step_index: number;
  title: string;
  description: string;
  verified_output_summary: string;
  artifacts_produced: string[];
  timestamp: string;
}

export interface FailedAttemptItemDTO {
  attempt_id: string;
  step_index: number;
  action_attempted: string;
  error_type: string;
  error_summary: string;
  dead_end_pattern: string;
  prohibited_rule: string;
  lessons_learned: string;
  timestamp: string;
}

export interface UserSteeringItemDTO {
  steering_id: string;
  turn_index: number;
  instruction_raw: string;
  distilled_constraint: string;
  scope: string;
  is_active: boolean;
  timestamp: string;
}

export interface RecordMilestoneRequestDTO {
  task_id: string;
  session_id: string;
  initial_goal?: string;
  step_index: number;
  title: string;
  verified_output_summary: string;
  description?: string;
  artifacts_produced?: string[];
}

export interface RecordFailedAttemptRequestDTO {
  task_id: string;
  session_id: string;
  initial_goal?: string;
  step_index: number;
  action_attempted: string;
  error_type: string;
  error_summary: string;
  dead_end_pattern: string;
  prohibited_rule: string;
  lessons_learned?: string;
}

export interface RecordUserSteeringRequestDTO {
  task_id: string;
  session_id: string;
  initial_goal?: string;
  turn_index: number;
  instruction_raw: string;
  distilled_constraint: string;
  scope?: string;
}

export interface CheckActionRequestDTO {
  task_id: string;
  action_text: string;
}

export interface CheckActionResponseDTO {
  is_prohibited: boolean;
  matched_rule: string | null;
  error_summary: string | null;
  matched_pattern: string | null;
}

export interface AntiLoopSnapshotResponseDTO {
  task_id: string;
  snapshot_token_estimate: number;
  dead_end_rules_injected: string[];
  active_user_steerings_injected: string[];
  latest_milestone_title: string | null;
  formatted_prompt_block: string;
}

export interface TaskTrajectoryBlackboxResponseDTO {
  task_id: string;
  session_id: string;
  initial_goal: string;
  status: string;
  version: number;
  milestones: MilestoneItemDTO[];
  failed_attempts: FailedAttemptItemDTO[];
  user_steerings: UserSteeringItemDTO[];
  created_at: string;
  updated_at: string;
}

export async function recordMilestone(
  req: RecordMilestoneRequestDTO,
): Promise<MilestoneItemDTO> {
  return apiRequest<MilestoneItemDTO>('/memory/triad-trajectory/milestone', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function recordFailedAttempt(
  req: RecordFailedAttemptRequestDTO,
): Promise<FailedAttemptItemDTO> {
  return apiRequest<FailedAttemptItemDTO>('/memory/triad-trajectory/failed-attempt', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function recordUserSteering(
  req: RecordUserSteeringRequestDTO,
): Promise<UserSteeringItemDTO> {
  return apiRequest<UserSteeringItemDTO>('/memory/triad-trajectory/steering', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function checkActionProhibited(
  req: CheckActionRequestDTO,
): Promise<CheckActionResponseDTO> {
  return apiRequest<CheckActionResponseDTO>('/memory/triad-trajectory/check-action', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function getAntiLoopSnapshot(
  taskId: string,
  stepHint = '',
  maxTokens = 150,
): Promise<AntiLoopSnapshotResponseDTO> {
  const query = new URLSearchParams();
  if (stepHint) query.set('step_hint', stepHint);
  query.set('max_tokens', String(maxTokens));
  return apiRequest<AntiLoopSnapshotResponseDTO>(
    `/memory/triad-trajectory/${encodeURIComponent(taskId)}/anti-loop-snapshot?${query.toString()}`,
  );
}

export async function getTaskBlackbox(
  taskId: string,
): Promise<TaskTrajectoryBlackboxResponseDTO> {
  return apiRequest<TaskTrajectoryBlackboxResponseDTO>(
    `/memory/triad-trajectory/${encodeURIComponent(taskId)}/blackbox`,
  );
}
