/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Types: CorrectionIntentKindEnum, MutationActionEnum, CorrectionSlotDTO,
 *        TargetNodeCandidateDTO, LiveCorrectionMutationResultDTO,
 *        CorrectionAckReceiptDTO, ProcessUtteranceRequest,
 *        LiveCorrectionHistoryResponse, LiveCorrectionStatusResponse
 * Functions: processLiveCorrection, fetchCorrectionCandidates,
 *            fetchCorrectionHistory, fetchCorrectionStatus, resetCorrectionPool
 *
 * [POS]
 * Client service for Item 128 Natural Language Memory Feedback & Live Correction Suite.
 * Aligns strictly with server /memory/live-correction/* endpoints.
 * Strict typing applied: Zero `any` types allowed. Single file < 200 lines.
 */

import { apiRequest } from '@/lib/api';

export type CorrectionIntentKindEnum =
  | 'preference_update'
  | 'fact_superseded'
  | 'behavior_rule'
  | 'retract_mistake'
  | 'general_amendment';

export type MutationActionEnum = 'supersede' | 'retract' | 'amend' | 'create_novel';

export interface CorrectionSlotDTO {
  corrected_value: string;
  negated_value?: string | null;
  subject?: string | null;
  intent: CorrectionIntentKindEnum;
  confidence: number;
  raw_utterance: string;
}

export interface TargetNodeCandidateDTO {
  memory_id: string;
  content: string;
  cube_id?: string | null;
  match_score: number;
  attributes: Record<string, string>;
}

export interface LiveCorrectionMutationResultDTO {
  action: MutationActionEnum;
  target_memory_id?: string | null;
  new_memory_id?: string | null;
  status: string;
  superseded_content?: string | null;
  new_content?: string | null;
  audit_trail: Record<string, string>;
  timestamp: string;
}

export interface CorrectionAckReceiptDTO {
  success: boolean;
  ack_message: string;
  intent: CorrectionIntentKindEnum;
  slot: CorrectionSlotDTO;
  mutated_record?: LiveCorrectionMutationResultDTO | null;
  processing_ms: number;
}

export interface ProcessUtteranceRequest {
  utterance: string;
  candidates?: TargetNodeCandidateDTO[];
}

export interface LiveCorrectionHistoryResponse {
  history: LiveCorrectionMutationResultDTO[];
  total: number;
}

export interface LiveCorrectionStatusResponse {
  service_status: string;
  candidates_count: number;
  mutations_count: number;
}

export async function processLiveCorrection(
  req: ProcessUtteranceRequest
): Promise<CorrectionAckReceiptDTO> {
  return apiRequest<CorrectionAckReceiptDTO>('/memory/live-correction/process', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function fetchCorrectionCandidates(): Promise<TargetNodeCandidateDTO[]> {
  return apiRequest<TargetNodeCandidateDTO[]>('/memory/live-correction/candidates', {
    method: 'GET',
  });
}

export async function fetchCorrectionHistory(): Promise<LiveCorrectionHistoryResponse> {
  return apiRequest<LiveCorrectionHistoryResponse>('/memory/live-correction/history', {
    method: 'GET',
  });
}

export async function fetchCorrectionStatus(): Promise<LiveCorrectionStatusResponse> {
  return apiRequest<LiveCorrectionStatusResponse>('/memory/live-correction/status', {
    method: 'GET',
  });
}

export async function resetCorrectionPool(): Promise<LiveCorrectionStatusResponse> {
  return apiRequest<LiveCorrectionStatusResponse>('/memory/live-correction/reset', {
    method: 'POST',
  });
}
