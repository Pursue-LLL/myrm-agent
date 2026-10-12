/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: Frontend API client transport)
 *
 * [OUTPUT]
 * Cross-Source Context Fabric & Project Entity Linker DTOs and API clients:
 * - registerProject: Register or update a project entry in workspace registry
 * - listProjects: List all registered canonical projects
 * - extractContextEntities: Extract people, commitments, blockers, and modules
 * - linkTextToProjects: Match text against active projects with confidence scoring
 * - sinkProjectInsight: Sink derived conclusion into targeted project memory
 *
 * [POS]
 * Frontend API service for Item 153 CrossSourceWorkContextFabricAndProjectEntityLinkerSuite.
 * Strict typing applied: 0 any types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface WorkContextEntityDTO {
  entity_id: string;
  entity_type: string;
  name: string;
  role_or_relation: string;
  temporal_anchor: string | null;
  status: string;
  confidence: number;
  evidence_snippet: string;
}

export interface ProjectRegistryEntryDTO {
  project_id: string;
  name: string;
  aliases: string[];
  keywords: string[];
  description: string;
  status: string;
}

export interface EntityMatchResultDTO {
  project_id: string;
  project_name: string;
  confidence_score: number;
  matched_terms: string[];
  evidence_snippet: string;
  is_definitive: boolean;
}

export interface ExtractEntitiesRequestDTO {
  text: string;
  source_kind?: string;
}

export interface ExtractEntitiesResponseDTO {
  entities: WorkContextEntityDTO[];
  total_count: number;
}

export interface LinkEntitiesRequestDTO {
  text: string;
  min_confidence?: number;
}

export interface LinkEntitiesResponseDTO {
  matches: EntityMatchResultDTO[];
  top_project_id: string | null;
}

export interface InsightCandidateDTO {
  insight_id: string;
  title: string;
  content: string;
  source_event_ids?: string[];
  target_project_id?: string | null;
  impact_level?: string;
}

export interface InsightSinkRequestDTO {
  candidate: InsightCandidateDTO;
  workspace_dir?: string | null;
  target_file_type?: string;
}

export interface InsightSinkResponseDTO {
  success: boolean;
  record_id: string | null;
  project_id: string | null;
  sink_target: string | null;
  provenance_tag: string | null;
  rendered_bullet: string | null;
  message: string;
}

export async function registerProject(
  entry: ProjectRegistryEntryDTO,
): Promise<ProjectRegistryEntryDTO> {
  return apiRequest<ProjectRegistryEntryDTO>('/memory/context-fabric/projects', {
    method: 'POST',
    body: JSON.stringify(entry),
  });
}

export async function listProjects(): Promise<ProjectRegistryEntryDTO[]> {
  return apiRequest<ProjectRegistryEntryDTO[]>('/memory/context-fabric/projects', {
    method: 'GET',
  });
}

export async function extractContextEntities(
  payload: ExtractEntitiesRequestDTO,
): Promise<ExtractEntitiesResponseDTO> {
  return apiRequest<ExtractEntitiesResponseDTO>('/memory/context-fabric/extract', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function linkTextToProjects(
  payload: LinkEntitiesRequestDTO,
): Promise<LinkEntitiesResponseDTO> {
  return apiRequest<LinkEntitiesResponseDTO>('/memory/context-fabric/link', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function sinkProjectInsight(
  payload: InsightSinkRequestDTO,
): Promise<InsightSinkResponseDTO> {
  return apiRequest<InsightSinkResponseDTO>('/memory/context-fabric/sink', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
