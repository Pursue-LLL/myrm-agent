/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Types: DreamMotiveTypeEnum, DreamTargetMemoryTypeEnum, DreamCognitiveActionTypeEnum,
 *        EvidenceAnchorDTO, MemoryFactPayloadDTO, SessionFragmentPayloadDTO,
 *        CognitiveConsolidationRequestDTO, HypotheticalDeductionDTO,
 *        DreamCognitiveActionDTO, GrowthDiaryEntryDTO, CognitiveConsolidationReportDTO,
 *        DreamCognitiveOverviewDTO
 * Functions: triggerCognitiveConsolidation, listGrowthDiaries, getGrowthDiaryEntry,
 *            getGrowthDiaryMarkdown, getDreamCognitiveOverview
 *
 * [POS]
 * Client service for Item 125 Dream Cognitive Consolidation & Growth Diary Suite.
 * Aligns with server /memory/dream-cognitive/* endpoints.
 * Strict typing applied: No `any` types allowed. Single file < 200 lines.
 */

import { apiRequest } from '@/lib/api';

export type DreamMotiveTypeEnum = 'newness' | 'frequency' | 'conflict' | 'feedback' | 'fragmentation';

export type DreamTargetMemoryTypeEnum = 'profile' | 'skill' | 'rule' | 'insight' | 'archive';

export type DreamCognitiveActionTypeEnum = 'create' | 'update' | 'merge' | 'archive';

export interface EvidenceAnchorDTO {
  message_id: string;
  speaker: string;
  verbatim_quote: string;
}

export interface MemoryFactPayloadDTO {
  fact_id?: string | null;
  content: string;
  evidence?: EvidenceAnchorDTO[];
}

export interface SessionFragmentPayloadDTO {
  session_id: string;
  project_id?: string | null;
  chat_turn_count: number;
  memories: MemoryFactPayloadDTO[];
}

export interface CognitiveConsolidationRequestDTO {
  fragments: SessionFragmentPayloadDTO[];
  cube_id?: string | null;
  target_project_id?: string | null;
}

export interface HypotheticalDeductionDTO {
  hypothetical_query: string;
  improved_response_reasoning: string;
  confidence_gain: number;
}

export interface DreamCognitiveActionDTO {
  action_id: string;
  action_type: DreamCognitiveActionTypeEnum;
  target_type: DreamTargetMemoryTypeEnum;
  target_id?: string | null;
  source_fact_ids: string[];
  payload_statement: string;
  deduction: HypotheticalDeductionDTO;
  confidence: number;
  cube_id?: string | null;
}

export interface GrowthDiaryEntryDTO {
  diary_id: string;
  title: string;
  summary: string;
  reflective_narrative: string;
  motive_type: DreamMotiveTypeEnum;
  themes: string[];
  cube_id?: string | null;
  generated_actions: DreamCognitiveActionDTO[];
  created_at: string;
}

export interface CognitiveConsolidationReportDTO {
  run_id: string;
  cube_id?: string | null;
  timestamp: string;
  duration_ms: number;
  input_fact_count: number;
  clusters_formed: number;
  actions_generated: number;
  diary_entries: GrowthDiaryEntryDTO[];
}

export interface DreamCognitiveOverviewDTO {
  total_diaries: number;
  total_actions: number;
  active_cubes: string[];
  latest_run_id?: string | null;
}

export async function triggerCognitiveConsolidation(
  payload: CognitiveConsolidationRequestDTO,
): Promise<CognitiveConsolidationReportDTO> {
  return apiRequest<CognitiveConsolidationReportDTO>('/memory/dream-cognitive/consolidate', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function listGrowthDiaries(cubeId?: string, limit: number = 20): Promise<GrowthDiaryEntryDTO[]> {
  const params = new URLSearchParams();
  if (cubeId) {
    params.append('cube_id', cubeId);
  }
  params.append('limit', limit.toString());
  return apiRequest<GrowthDiaryEntryDTO[]>(`/memory/dream-cognitive/diaries?${params.toString()}`, {
    method: 'GET',
  });
}

export async function getGrowthDiaryEntry(diaryId: string): Promise<GrowthDiaryEntryDTO> {
  return apiRequest<GrowthDiaryEntryDTO>(`/memory/dream-cognitive/diaries/${encodeURIComponent(diaryId)}`, {
    method: 'GET',
  });
}

export async function getGrowthDiaryMarkdown(diaryId: string): Promise<string> {
  return apiRequest<string>(`/memory/dream-cognitive/diaries/${encodeURIComponent(diaryId)}/markdown`, {
    method: 'GET',
  });
}

export async function getDreamCognitiveOverview(): Promise<DreamCognitiveOverviewDTO> {
  return apiRequest<DreamCognitiveOverviewDTO>('/memory/dream-cognitive/overview', { method: 'GET' });
}
