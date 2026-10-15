/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Sovereign Asset Package Migration and Cross-Host Restore DTOs and API clients:
 * - exportSovereignBundle
 * - restoreSovereignBundle
 * - detectCompetitors
 * - ingestCompetitor
 *
 * [POS]
 * Frontend API client for portable .myrmpkg archive export, verified restore with path remapping, and competitor ingestion.
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface ExportBundleRequestDTO {
  source_dir?: string | null;
  output_bundle_path?: string | null;
  include_categories?: string[];
  custom_description?: string;
}

export interface ExportBundleResponseDTO {
  success: boolean;
  bundle_path: string;
  package_id: string;
  asset_count: number;
  total_bytes: number;
  sha256: string;
}

export interface RestoreBundleRequestDTO {
  bundle_path: string;
  target_destination_dir?: string | null;
  current_workspace_root?: string | null;
  overwrite_existing?: boolean;
}

export interface RestoreBundleResponseDTO {
  success: boolean;
  package_id: string;
  restored_assets: string[];
  remapped_paths_count: number;
  source_workspace_root: string;
  target_workspace_root: string;
}

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
 * Export digital sovereign assets into a verified .myrmpkg bundle.
 */
export async function exportSovereignBundle(
  req: ExportBundleRequestDTO = {}
): Promise<ExportBundleResponseDTO> {
  return apiRequest<ExportBundleResponseDTO>('/memory/migration/export', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

/**
 * Unpack, verify SHA-256 integrity, remap workspace paths, and restore .myrmpkg bundle.
 */
export async function restoreSovereignBundle(
  req: RestoreBundleRequestDTO
): Promise<RestoreBundleResponseDTO> {
  return apiRequest<RestoreBundleResponseDTO>('/memory/migration/restore', {
    method: 'POST',
    body: JSON.stringify(req),
  });
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
export async function ingestCompetitor(
  req: CompetitorIngestRequestDTO
): Promise<CompetitorIngestResponseDTO> {
  return apiRequest<CompetitorIngestResponseDTO>('/memory/migration/ingest-competitors', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}
