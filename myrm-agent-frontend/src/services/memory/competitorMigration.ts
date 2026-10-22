/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Competitor assistant migration DTOs and API clients:
 * - detectCompetitors
 * - ingestCompetitor
 *
 * [POS]
 * Frontend API client for detecting third-party assistant assets on this machine (Hermes, Claude Code, Codex)
 * and translating them into Myrm memories, skills and rules.
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface CompetitorDetectResponseDTO {
  detected_competitors: string[];
  hermes_dir?: string | null;
  claude_code_rule_path?: string | null;
  codex_rule_path?: string | null;
}

export interface CompetitorIngestRequestDTO {
  competitor: string;
  source_path: string;
  target_destination_dir?: string | null;
}

export interface CompetitorIngestResponseDTO {
  success: boolean;
  imported_rules_count: number;
  imported_skills_count: number;
  imported_memories_count: number;
  details: string[];
}

/**
 * Probe workstation for third-party competitor assistant assets (Hermes, Claude Code, Codex).
 */
export async function detectCompetitors(): Promise<CompetitorDetectResponseDTO> {
  return apiRequest<CompetitorDetectResponseDTO>('/memory/migration/detect-competitors', {
    method: 'GET',
  });
}

/**
 * Ingest and translate competitor memories, skills, and rules into Myrm.
 */
export async function ingestCompetitor(req: CompetitorIngestRequestDTO): Promise<CompetitorIngestResponseDTO> {
  return apiRequest<CompetitorIngestResponseDTO>('/memory/migration/ingest-competitors', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}
