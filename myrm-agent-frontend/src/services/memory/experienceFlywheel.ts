/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: Frontend API client transport)
 *
 * [OUTPUT]
 * Project Experience & ADR Flywheel DTOs and API clients:
 * - extractExperiences: Extract Bug experiences and ADR items from task narrative
 * - ingestExperience: Ingest an experience into causal flywheel with optional dongle sync
 * - listExperiences: Retrieve all ingested experiences from flywheel
 * - sniffMinefield: Pre-sniff upcoming execution plan against historical danger zones
 *
 * [POS]
 * Frontend API service for Item 154 ProjectExperienceAndADRFlywheelSuite.
 * Strict typing applied: 0 any types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface EngineeringExperienceDTO {
  experience_id: string;
  kind: string;
  target_entity: string;
  trigger_condition: string;
  root_cause_or_rationale: string;
  convention_or_remedy: string;
  created_date: string;
  tags?: string[];
  confidence?: number;
}

export interface ExtractExperienceRequestDTO {
  narrative: string;
  default_kind?: string;
}

export interface ExtractExperienceResponseDTO {
  experiences: EngineeringExperienceDTO[];
  total_count: number;
}

export interface IngestExperienceRequestDTO {
  experience: EngineeringExperienceDTO;
  workspace_dir?: string | null;
}

export interface IngestExperienceResponseDTO {
  experience_id: string;
  kind: string;
  target_entity: string;
  bound_dongle_block_id: string | null;
  persisted: boolean;
  message: string;
}

export interface MinefieldAlertDTO {
  entity_matched: string;
  experience_id: string;
  kind: string;
  warning_message: string;
  convention_to_follow: string;
  severity: string;
}

export interface SniffMinefieldRequestDTO {
  plan_text: string;
  explicit_entities?: string[];
}

export interface SniffMinefieldResponseDTO {
  alerts: MinefieldAlertDTO[];
  advisory_prompt: string;
  has_critical_alerts: boolean;
}

export async function extractExperiences(
  payload: ExtractExperienceRequestDTO,
): Promise<ExtractExperienceResponseDTO> {
  return apiRequest<ExtractExperienceResponseDTO>('/memory/experience-flywheel/extract', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function ingestExperience(
  payload: IngestExperienceRequestDTO,
): Promise<IngestExperienceResponseDTO> {
  return apiRequest<IngestExperienceResponseDTO>('/memory/experience-flywheel/ingest', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function listExperiences(
  kind?: string,
): Promise<EngineeringExperienceDTO[]> {
  const query = kind ? `?kind=${encodeURIComponent(kind)}` : '';
  return apiRequest<EngineeringExperienceDTO[]>(`/memory/experience-flywheel/list${query}`, {
    method: 'GET',
  });
}

export async function sniffMinefield(
  payload: SniffMinefieldRequestDTO,
): Promise<SniffMinefieldResponseDTO> {
  return apiRequest<SniffMinefieldResponseDTO>('/memory/experience-flywheel/sniff', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
