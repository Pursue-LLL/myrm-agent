/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Cross-Agent Composable Context & Conflict Arbitration DTOs and API clients:
 * - projectComposableContext
 * - arbitrateMemoryConflict
 * - sealTaskHandoff
 * - verifyTaskHandoff
 *
 * [POS]
 * Frontend API client for multi-agent context projection, divergence arbitration, and sealed task handoffs.
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface ContextLayerDTO {
  layer_kind: string;
  title: string;
  content: string;
  token_count: number;
  content_hash: string;
  is_shared: boolean;
}

export interface ProjectComposableContextRequestDTO {
  agent_id: string;
  session_id: string;
  global_ground_truth?: string[];
  profile_tools_memory?: string[];
  private_scratchpad?: string | null;
  token_budget?: number;
}

export interface ComposableContextResponseDTO {
  agent_id: string;
  session_id: string;
  total_tokens: number;
  layers: ContextLayerDTO[];
  assembled_prompt_text: string;
  cache_prefix_hash: string;
}

export interface MemoryAssertionDTO {
  assertion_id: string;
  subject: string;
  predicate: string;
  object_value: string;
  confidence: number;
  source_agent_id: string;
  source_reference?: string | null;
  timestamp?: number;
}

export interface ArbitrateConflictRequestDTO {
  divergence_id?: string | null;
  subject: string;
  predicate: string;
  assertion_a: MemoryAssertionDTO;
  assertion_b: MemoryAssertionDTO;
  workspace_root?: string | null;
}

export interface ArbitrationOutcomeDTO {
  divergence_id: string;
  resolved: boolean;
  policy_applied: string;
  winning_assertion: MemoryAssertionDTO;
  audit_rationale: string;
  requires_human_confirmation: boolean;
}

export interface SealHandoffRequestDTO {
  source_agent_id: string;
  target_agent_id: string;
  task_id: string;
  context_snapshot: string;
  critical_assertions?: MemoryAssertionDTO[];
  secret_salt?: string;
}

export interface HandoffPacketDTO {
  packet_id: string;
  source_agent_id: string;
  target_agent_id: string;
  task_id: string;
  context_snapshot: string;
  critical_assertions: MemoryAssertionDTO[];
  timestamp: number;
  signature_sha256: string;
}

export interface VerifyHandoffRequestDTO {
  packet: HandoffPacketDTO;
  secret_salt?: string;
}

export interface HandoffVerificationResponseDTO {
  packet_id: string;
  is_valid: boolean;
  verified_assertions_count: number;
  rejection_reason?: string | null;
}

/**
 * Compose 4-layer virtual reference context preserving 80%+ prefix cache.
 */
export async function projectComposableContext(
  req: ProjectComposableContextRequestDTO
): Promise<ComposableContextResponseDTO> {
  return apiRequest<ComposableContextResponseDTO>('/memory/cross-agent/project-context', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

/**
 * Settle memory divergence between two agents using physical ground truth or coordinator authority.
 */
export async function arbitrateMemoryConflict(
  req: ArbitrateConflictRequestDTO
): Promise<ArbitrationOutcomeDTO> {
  return apiRequest<ArbitrationOutcomeDTO>('/memory/cross-agent/arbitrate-conflict', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

/**
 * Seal an outgoing task handoff packet with cryptographic SHA-256 signature.
 */
export async function sealTaskHandoff(
  req: SealHandoffRequestDTO
): Promise<HandoffPacketDTO> {
  return apiRequest<HandoffPacketDTO>('/memory/cross-agent/seal-handoff', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

/**
 * Verify cryptographic seal of incoming task handoff packet.
 */
export async function verifyTaskHandoff(
  req: VerifyHandoffRequestDTO
): Promise<HandoffVerificationResponseDTO> {
  return apiRequest<HandoffVerificationResponseDTO>('/memory/cross-agent/verify-handoff', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}
