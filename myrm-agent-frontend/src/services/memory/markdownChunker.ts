/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Types: ChunkingConfigDTO, MarkdownChunkDTO, ChunkSliceRequest, ChunkSliceResponse,
 *        IncrementalDiffReportDTO, IncrementalIndexRequest, IncrementalIndexResponse,
 *        HydrateRequest, HydrateResponse
 * Functions: sliceMarkdown, incrementalIndexMarkdown, hydrateChunkContext
 *
 * [POS]
 * Client service for Item 132 IncrementalSlidingWindowMarkdownChunkerSuite.
 * Manages semantic sliding window slicing, 80-token overlap, line pointers,
 * content-hash incremental diffing, and context hydration.
 * Strictly typed with zero `any` usage. Single file < 200 lines.
 */

import { apiRequest } from '@/lib/api';

export interface ChunkingConfigDTO {
  target_tokens: number;
  overlap_tokens: number;
  chars_per_token?: number;
  max_chunk_chars?: number;
}

export interface MarkdownChunkDTO {
  chunk_id: string;
  source_path: string;
  start_line: number;
  end_line: number;
  char_start: number;
  char_end: number;
  text: string;
  chunk_hash: string;
  token_estimate: number;
  is_truncated: boolean;
}

export interface ChunkSliceRequest {
  content: string;
  source_path?: string;
  config?: ChunkingConfigDTO | null;
}

export interface ChunkSliceResponse {
  source_path: string;
  total_chunks: number;
  chunks: MarkdownChunkDTO[];
}

export interface IncrementalDiffReportDTO {
  source_path: string;
  total_chunks: number;
  reused_chunks: number;
  changed_chunks: number;
  deleted_chunks: number;
  token_savings_pct: number;
  status: 'unchanged' | 'partially_updated' | 'fully_reindexed' | string;
  timestamp: string;
}

export interface IncrementalIndexRequest {
  source_path: string;
  new_content: string;
  config?: ChunkingConfigDTO | null;
}

export interface IncrementalIndexResponse {
  report: IncrementalDiffReportDTO;
  chunks: MarkdownChunkDTO[];
}

export interface HydrateRequest {
  chunk: MarkdownChunkDTO;
  full_document: string;
  window_lines?: number;
}

export interface HydrateResponse {
  hydrated_text: string;
  window_lines: number;
  start_line: number;
  end_line: number;
}

export async function sliceMarkdown(
  req: ChunkSliceRequest
): Promise<ChunkSliceResponse> {
  return apiRequest<ChunkSliceResponse>('/memory/chunker/slice', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function incrementalIndexMarkdown(
  req: IncrementalIndexRequest
): Promise<IncrementalIndexResponse> {
  return apiRequest<IncrementalIndexResponse>(
    '/memory/chunker/incremental-index',
    {
      method: 'POST',
      body: JSON.stringify(req),
    }
  );
}

export async function hydrateChunkContext(
  req: HydrateRequest
): Promise<HydrateResponse> {
  return apiRequest<HydrateResponse>('/memory/chunker/hydrate', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}
