/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API client transport)
 *
 * [OUTPUT]
 * Tool-Noise-Free Memory Extraction and Purge Generation Epoch DTOs & API clients:
 * - cleanDialogue
 * - inspectPII
 * - commitFact
 * - purgeNoiseFreeMemory
 * - getEpochStatus
 * - getUserFacts
 *
 * [POS]
 * Frontend API service for Topic 01 Item 88 (Anthropic Commerce Agents-style memory isolation,
 * PII regex screening, and monotonic epoch fencing).
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface ConversationTurnDTO {
  role: 'user' | 'assistant' | 'tool' | 'system';
  content: string;
  tool_calls?: Array<{ name: string; args: string }>;
  tool_call_id?: string;
}

export interface CleanDialogueRequestDTO {
  user_id?: string;
  turns: ConversationTurnDTO[];
}

export interface CleanDialogueResponseDTO {
  user_id: string;
  clean_transcript: string;
  observed_generation: number;
  tokens_saved: number;
  stripped_turns_count: number;
}

export interface PIIViolationDetailDTO {
  rule_name: string;
  snippet_masked: string;
  severity: string;
}

export interface InspectPIIRequestDTO {
  statement: string;
  mask_instead_of_reject?: boolean;
}

export interface InspectPIIResponseDTO {
  is_clean: boolean;
  sanitized_text: string;
  violations: PIIViolationDetailDTO[];
}

export interface ExtractedFactCandidateDTO {
  fact_id: string;
  fact_text: string;
  category?: string;
  confidence?: number;
  generation_observed: number;
  timestamp?: string;
}

export interface CommitFactRequestDTO {
  user_id?: string;
  candidate: ExtractedFactCandidateDTO;
}

export interface CommitFactResponseDTO {
  success: boolean;
  message: string;
  violation?: PIIViolationDetailDTO | null;
}

export interface PurgeMemoryRequestDTO {
  user_id?: string;
}

export interface PurgeMemoryResponseDTO {
  user_id: string;
  new_generation: number;
  purged_facts_count: number;
  timestamp: string;
}

export interface EpochStatusResponseDTO {
  user_id: string;
  current_generation: number;
  active_extractions: number;
  stale_writes_dropped: number;
  last_purged_at: string | null;
  stored_facts_count: number;
  pii_violations_blocked: number;
}

/**
 * Strips tool execution receipts and prepares noise-free transcript for extraction.
 */
export async function cleanDialogue(
  request: CleanDialogueRequestDTO
): Promise<CleanDialogueResponseDTO> {
  return apiRequest<CleanDialogueResponseDTO>('/memory/noise-free/clean-dialogue', {
    method: 'POST',
    body: JSON.stringify({
      user_id: request.user_id || 'default_user',
      turns: request.turns,
    }),
  });
}

/**
 * Inspects a statement using code-level PII regular expression screening.
 */
export async function inspectPII(
  request: InspectPIIRequestDTO
): Promise<InspectPIIResponseDTO> {
  return apiRequest<InspectPIIResponseDTO>('/memory/noise-free/inspect-pii', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Validates and commits an extracted memory fact against monotonic generation epoch fence and PII gate.
 */
export async function commitFact(
  request: CommitFactRequestDTO
): Promise<CommitFactResponseDTO> {
  return apiRequest<CommitFactResponseDTO>('/memory/noise-free/commit-fact', {
    method: 'POST',
    body: JSON.stringify({
      user_id: request.user_id || 'default_user',
      candidate: request.candidate,
    }),
  });
}

/**
 * Atomically clears memory and advances generation epoch to prevent stale async resurrection.
 */
export async function purgeNoiseFreeMemory(
  request: PurgeMemoryRequestDTO = {}
): Promise<PurgeMemoryResponseDTO> {
  return apiRequest<PurgeMemoryResponseDTO>('/memory/noise-free/purge', {
    method: 'POST',
    body: JSON.stringify({
      user_id: request.user_id || 'default_user',
    }),
  });
}

/**
 * Retrieves epoch fence status, current generation, and dropped stale write count.
 */
export async function getEpochStatus(
  userId = 'default_user'
): Promise<EpochStatusResponseDTO> {
  return apiRequest<EpochStatusResponseDTO>(
    `/memory/noise-free/status?user_id=${encodeURIComponent(userId)}`
  );
}

/**
 * Retrieves all currently persisted clean facts for user.
 */
export async function getUserFacts(
  userId = 'default_user'
): Promise<ExtractedFactCandidateDTO[]> {
  return apiRequest<ExtractedFactCandidateDTO[]>(
    `/memory/noise-free/facts?user_id=${encodeURIComponent(userId)}`
  );
}
