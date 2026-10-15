/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: Frontend API client transport)
 *
 * [OUTPUT]
 * Revocable Provenance-Qualified Memory & Dream Diary DTOs and API clients:
 * - saveProvenanceMemory, listProvenanceMemories
 * - forgetMemory (Atomic memory forget with transcript immutability guarantee)
 * - recordDreamDiary, listDreamDiaries (Transparent background consolidation diaries)
 *
 * [POS]
 * Frontend API service for Topic 01 Item 91 (Revocable Provenance-Qualified Memory
 * and Dream Diary Consolidation Suite).
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface ProvenanceMetadataDTO {
  session_id: string;
  message_id: string;
  turn_index: number;
  quote_snippet: string;
  extracted_at: string;
  confidence_score: number;
}

export interface ProvenanceQualifiedMemoryDTO {
  memory_id: string;
  statement: string;
  category: string;
  provenance: ProvenanceMetadataDTO;
  is_revoked: boolean;
  revoked_at: string | null;
  revocation_reason: string;
  created_at: string;
  updated_at: string;
}

export interface SaveProvenanceMemoryRequestDTO {
  memory_id?: string;
  statement: string;
  category?: string;
  session_id: string;
  message_id: string;
  turn_index?: number;
  quote_snippet: string;
  confidence_score?: number;
}

export interface ForgetMemoryRequestDTO {
  reason?: string;
}

export interface ForgetResultDTO {
  memory_id: string;
  revoked: boolean;
  source_session_id: string;
  source_message_id: string;
  message: string;
  transcript_intact: boolean;
}

export interface DreamDiaryEntryDTO {
  dream_id: string;
  agent_id: string;
  scanned_turns: number;
  promoted_memory_ids: string[];
  pruned_duplicates_count: number;
  duration_ms: number;
  status: string;
  notes: string;
  created_at: string;
}

export interface RecordDreamDiaryRequestDTO {
  agent_id: string;
  scanned_turns: number;
  promoted_memory_ids?: string[];
  pruned_duplicates_count?: number;
  duration_ms?: number;
  status?: string;
  notes?: string;
}

/**
 * Saves a new long-term memory with strict provenance origin metadata.
 */
export async function saveProvenanceMemory(
  request: SaveProvenanceMemoryRequestDTO
): Promise<ProvenanceQualifiedMemoryDTO> {
  return apiRequest<ProvenanceQualifiedMemoryDTO>('/memory/provenance/memories', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Lists stored memories with option to include revoked records.
 */
export async function listProvenanceMemories(
  includeRevoked = false
): Promise<ProvenanceQualifiedMemoryDTO[]> {
  const query = includeRevoked ? '?include_revoked=true' : '';
  return apiRequest<ProvenanceQualifiedMemoryDTO[]>(
    `/memory/provenance/memories${query}`
  );
}

/**
 * Atomically revokes a memory (memory forget) while preserving raw transcripts.
 */
export async function forgetMemory(
  memoryId: string,
  reason = ''
): Promise<ForgetResultDTO> {
  const query = reason ? `?reason=${encodeURIComponent(reason)}` : '';
  return apiRequest<ForgetResultDTO>(
    `/memory/provenance/memories/${encodeURIComponent(memoryId)}/forget${query}`,
    {
      method: 'DELETE',
    }
  );
}

/**
 * Logs a completed background dream consolidation cycle.
 */
export async function recordDreamDiary(
  request: RecordDreamDiaryRequestDTO
): Promise<DreamDiaryEntryDTO> {
  return apiRequest<DreamDiaryEntryDTO>('/memory/provenance/dream-diaries', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Lists recorded dream consolidation diaries in reverse chronological order.
 */
export async function listDreamDiaries(
  agentId?: string,
  limit = 50
): Promise<DreamDiaryEntryDTO[]> {
  const params = new URLSearchParams();
  if (agentId) {
    params.set('agent_id', agentId);
  }
  if (limit) {
    params.set('limit', String(limit));
  }
  const query = params.toString() ? `?${params.toString()}` : '';
  return apiRequest<DreamDiaryEntryDTO[]>(
    `/memory/provenance/dream-diaries${query}`
  );
}
