/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Types: SqliteVecStatsResponse, SqliteVecSearchRequest, SqliteVecSearchItem,
 *        SqliteVecSearchResponse
 * Functions: fetchSqliteVecStats, searchSqliteVec
 *
 * [POS]
 * Client service for Item 130 SqliteVec Embedded Zero-Dependency Vector Store Suite.
 * Aligns strictly with server /memory/sqlite-vec/* endpoints.
 * Strict typing applied: Zero `any` types allowed. Single file < 200 lines.
 */

import { apiRequest } from '@/lib/api';

export type SqliteVecEngineMode = 'native_vec0' | 'process_blob';

export interface SqliteVecStatsResponse {
  engine_mode: SqliteVecEngineMode | string;
  is_persistent: boolean;
  db_path: string;
  file_size_bytes: number;
  collection_count: number;
  total_documents: number;
  status: string;
}

export interface SqliteVecSearchRequest {
  collection?: string;
  query_vector: number[];
  limit?: number;
  apply_decay?: boolean;
  half_life_seconds?: number | null;
  score_threshold?: number | null;
}

export interface SqliteVecSearchItem {
  id: string;
  content: string;
  score: number;
  raw_similarity?: number | null;
  decay_factor?: number | null;
  metadata: Record<string, string | number | boolean | string[]>;
}

export interface SqliteVecSearchResponse {
  collection: string;
  results: SqliteVecSearchItem[];
  total_returned: number;
  apply_decay: boolean;
  execution_mode: string;
}

export async function fetchSqliteVecStats(): Promise<SqliteVecStatsResponse> {
  return apiRequest<SqliteVecStatsResponse>('/memory/sqlite-vec/stats', {
    method: 'GET',
  });
}

export async function searchSqliteVec(
  req: SqliteVecSearchRequest
): Promise<SqliteVecSearchResponse> {
  return apiRequest<SqliteVecSearchResponse>('/memory/sqlite-vec/search', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}
