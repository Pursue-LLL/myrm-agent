/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * getExternalTranscriptStatus, syncExternalTranscripts: API client for external agent transcript recall.
 *
 * [POS]
 * External agent transcript synchronization API client.
 * Manages incremental indexing and cloud file uploads for Claude Code & Codex sessions.
 */

import { apiRequest } from '@/lib/api';

export interface ExternalTranscriptStatus {
  enabled: boolean;
  tracked_files_count: number;
  last_synced_at: string | null;
  default_directory: string;
}

export interface ExternalFilePayload {
  filename: string;
  content: string;
}

export interface ExternalTranscriptSyncRequest {
  directory_path?: string;
  source?: string;
  uploaded_files?: ExternalFilePayload[];
}

export interface ExternalTranscriptSyncResult {
  synced_files: number;
  new_turns: number;
  affected_chats: string[];
  skipped_files: number;
  errors: string[];
}

export async function getExternalTranscriptStatus(): Promise<ExternalTranscriptStatus> {
  return (await apiRequest('/memory/external-transcripts/status', {
    method: 'GET',
  })) as ExternalTranscriptStatus;
}

export async function syncExternalTranscripts(
  req: ExternalTranscriptSyncRequest,
): Promise<ExternalTranscriptSyncResult> {
  return (await apiRequest('/memory/external-transcripts/sync', {
    method: 'POST',
    body: JSON.stringify(req),
  })) as ExternalTranscriptSyncResult;
}
