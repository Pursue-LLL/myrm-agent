/**
 * External session transcript import API service.
 *
 * [INPUT]
 * @/lib/api::apiRequest, getApiBaseUrl
 *
 * [OUTPUT]
 * - ImportTranscriptResult interface
 * - importTranscriptJson, importTranscriptFile
 *
 * [POS]
 * Client HTTP boundary for importing Claude Code, Codex, and Hermes session transcripts.
 */

import { apiRequest } from '@/lib/api';

export interface ImportTranscriptResult {
  ok: boolean;
  chat_id: string;
  title: string;
  turns_count: number;
  source_platform: string;
  raw_tokens_estimate: number;
  clean_tokens_estimate: number;
  reduction_ratio: number;
}

export interface ImportTranscriptJsonRequest {
  raw_content: string;
  source_hint?: string;
  target_workspace?: string;
  target_agent_id?: string;
  title_override?: string;
}

export interface ImportTranscriptFileOptions {
  source_hint?: string;
  target_workspace?: string;
  target_agent_id?: string;
  title_override?: string;
}

export const importTranscriptJson = async (req: ImportTranscriptJsonRequest): Promise<ImportTranscriptResult> => {
  return apiRequest<ImportTranscriptResult>('/chats/import-transcript', {
    method: 'POST',
    body: JSON.stringify(req),
  });
};

export const importTranscriptFile = async (
  file: File,
  options?: ImportTranscriptFileOptions,
): Promise<ImportTranscriptResult> => {
  const formData = new FormData();
  formData.append('file', file);
  if (options?.source_hint) {
    formData.append('source_hint', options.source_hint);
  }
  if (options?.target_workspace) {
    formData.append('target_workspace', options.target_workspace);
  }
  if (options?.target_agent_id) {
    formData.append('target_agent_id', options.target_agent_id);
  }
  if (options?.title_override) {
    formData.append('title_override', options.title_override);
  }

  return apiRequest<ImportTranscriptResult>('/chats/import-transcript/file', {
    method: 'POST',
    body: formData,
  });
};
