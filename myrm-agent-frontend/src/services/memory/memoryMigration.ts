/**
 * Multi-platform memory migration and import wizard client service.
 * Discovers competitor assets, previews normalized cognitive facts, and ingests with 400/80 sliding chunks.
 */

import { apiClient } from '@/services/api';

export type MigrationSourceType =
  | 'openclaw'
  | 'hermes'
  | 'chatgpt_export'
  | 'claude_project'
  | 'memos'
  | 'markdown_tree'
  | 'generic_json';

export interface DetectedCandidateDTO {
  source_type: MigrationSourceType;
  artifact_path: string;
  estimated_entries: number;
  summary: string;
}

export interface MigrationDetectRequestDTO {
  custom_candidates?: string[];
}

export interface MigrationDetectResponseDTO {
  total_detected: number;
  candidates: DetectedCandidateDTO[];
}

export interface ExtractedMemoryUnitDTO {
  source_type: MigrationSourceType;
  source_id: string;
  normalized_text: string;
  layer: string;
  tags: string[];
  content_hash: string;
}

export interface MigrationPreviewRequestDTO {
  source_type: MigrationSourceType;
  file_path?: string;
  raw_content?: string;
  source_label?: string;
}

export interface MigrationPreviewResponseDTO {
  total_extracted: number;
  units: ExtractedMemoryUnitDTO[];
}

export interface MigrationImportRequestDTO {
  source_type: MigrationSourceType;
  file_path?: string;
  raw_content?: string;
  source_label?: string;
}

export interface MigrationRunReportDTO {
  migration_id: string;
  source_type: MigrationSourceType;
  source_path: string;
  total_scanned: number;
  total_admitted: number;
  total_skipped_duplicates: number;
  total_chunks_generated: number;
  vector_ingestion_status: string;
  latency_ms: number;
  timestamp: number;
}

export interface MigrationImportResponseDTO {
  success: boolean;
  report: MigrationRunReportDTO;
}

export interface MigrationSourcesListResponseDTO {
  supported_sources: MigrationSourceType[];
}

export const memoryMigrationService = {
  /**
   * List all supported competitor platforms and memory formats.
   */
  async listSources(): Promise<MigrationSourcesListResponseDTO> {
    return apiClient.get<MigrationSourcesListResponseDTO>(
      '/memory/migration-wizard/sources'
    );
  },

  /**
   * Scan local filesystem/workspace to discover competitor memory archives.
   */
  async detectAssets(
    request: MigrationDetectRequestDTO = {}
  ): Promise<MigrationDetectResponseDTO> {
    return apiClient.post<MigrationDetectResponseDTO>(
      '/memory/migration-wizard/detect',
      request
    );
  },

  /**
   * Preview normalized cognitive memory facts before committing ingestion.
   */
  async previewMemory(
    request: MigrationPreviewRequestDTO
  ): Promise<MigrationPreviewResponseDTO> {
    return apiClient.post<MigrationPreviewResponseDTO>(
      '/memory/migration-wizard/preview',
      request
    );
  },

  /**
   * Execute one-click migration with fingerprint deduplication and sliding window chunking.
   */
  async importMemory(
    request: MigrationImportRequestDTO
  ): Promise<MigrationImportResponseDTO> {
    return apiClient.post<MigrationImportResponseDTO>(
      '/memory/migration-wizard/import',
      request
    );
  },
};
