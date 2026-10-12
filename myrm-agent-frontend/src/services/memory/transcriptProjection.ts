/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: Frontend API client transport)
 *
 * [OUTPUT]
 * SQLite Transcript Projection & Adoption DTOs and API clients:
 * - appendTranscriptEntries: Append raw transcript entries into the SQLite SSOT table
 * - ingestLiveMessages: Ingest live host session messages into working memory
 * - bootstrapSessionProjection: Idempotent cold-start bootstrap with duplicate disambiguation
 * - getSessionProjectedMessages: Retrieve working memory messages for a session
 * - getSessionTranscriptEntries: Retrieve raw transcript entries for a session
 *
 * [POS]
 * Frontend API service for Item 150 SqliteTranscriptProjectionSuite.
 * Strict typing applied: 0 any types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface TranscriptEntryDTO {
  entry_id: string;
  session_id: string;
  seq: number;
  role: string;
  content: string;
  created_at_ms?: number | null;
  parent_id?: string | null;
}

export interface SessionMessageDTO {
  message_id: string;
  session_id: string;
  seq: number;
  role: string;
  content: string;
  timestamp_ms?: number | null;
  transcript_entry_id?: string | null;
}

export interface AdoptionDecisionDTO {
  message_id: string;
  transcript_entry_id: string | null;
  status: string;
  reason: string;
}

export interface BootstrapSessionRequestDTO {
  session_id: string;
  session_key: string;
  agent_id?: string;
  tolerance_ms?: number;
}

export interface BootstrapSessionResponseDTO {
  session_id: string;
  bootstrapped: boolean;
  imported_messages: number;
  already_bootstrapped: boolean;
  decisions: AdoptionDecisionDTO[];
}

/**
 * Append raw transcript entries into the SQLite SSOT table.
 */
export async function appendTranscriptEntries(
  entries: TranscriptEntryDTO[]
): Promise<{ appended_count: number }> {
  return apiRequest<{ appended_count: number }>('/memory/transcript-projection/append', {
    method: 'POST',
    body: JSON.stringify(entries),
    headers: {
      'Content-Type': 'application/json',
    },
  });
}

/**
 * Ingest live host session messages into working memory.
 */
export async function ingestLiveMessages(
  messages: SessionMessageDTO[]
): Promise<{ ingested_count: number }> {
  return apiRequest<{ ingested_count: number }>('/memory/transcript-projection/ingest', {
    method: 'POST',
    body: JSON.stringify(messages),
    headers: {
      'Content-Type': 'application/json',
    },
  });
}

/**
 * Execute idempotent cold-start bootstrap projection with adoption disambiguation.
 */
export async function bootstrapSessionProjection(
  request: BootstrapSessionRequestDTO
): Promise<BootstrapSessionResponseDTO> {
  return apiRequest<BootstrapSessionResponseDTO>('/memory/transcript-projection/bootstrap', {
    method: 'POST',
    body: JSON.stringify(request),
    headers: {
      'Content-Type': 'application/json',
    },
  });
}

/**
 * Retrieve all working memory messages for the specified session in sequence order.
 */
export async function getSessionProjectedMessages(
  sessionId: string
): Promise<SessionMessageDTO[]> {
  return apiRequest<SessionMessageDTO[]>(
    `/memory/transcript-projection/${encodeURIComponent(sessionId)}/messages`,
    {
      method: 'GET',
    }
  );
}

/**
 * Retrieve all raw transcript entries for the specified session in sequence order.
 */
export async function getSessionTranscriptEntries(
  sessionId: string
): Promise<TranscriptEntryDTO[]> {
  return apiRequest<TranscriptEntryDTO[]>(
    `/memory/transcript-projection/${encodeURIComponent(sessionId)}/entries`,
    {
      method: 'GET',
    }
  );
}
