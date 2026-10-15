/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: Frontend API client transport)
 *
 * [OUTPUT]
 * Transparent Inspectable Model Private Notebook DTOs & API clients:
 * - listNotes, searchNotes, getNote, appendNote, rewriteNote, deleteNote (Notes 5 tools)
 * - listContexts, searchHistory (History tools)
 * - switchToNewContext (Cross-context smooth handover)
 *
 * [POS]
 * Frontend API service for Topic 01 Item 89 (OpenAI Codex rust-v0.153.0 PR #42385
 * context_management, human rectification via markdown note storage, and context rotation).
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface NoteMetadataDTO {
  title: string;
  char_count: number;
  line_count: number;
  updated_at: string;
  tags: string[];
}

export interface NoteEntryDTO {
  title: string;
  content: string;
  updated_at: string;
  tags: string[];
}

export interface AppendNoteRequestDTO {
  title: string;
  content: string;
  tags?: string[];
}

export interface RewriteNoteRequestDTO {
  title: string;
  content: string;
  tags?: string[];
}

export interface NoteSearchResultDTO {
  title: string;
  score: number;
  snippet: string;
}

export interface HistoryContextItemDTO {
  context_id: string;
  title: string;
  turn_count: number;
  created_at: string;
}

export interface HistoryEntryItemDTO {
  context_id: string;
  turn_index: number;
  role: string;
  content: string;
  created_at: string;
}

export interface NewContextRequestDTO {
  summary_reason: string;
  custom_new_id?: string;
}

export interface NewContextResponseDTO {
  new_context_id: string;
  previous_context_id: string;
  carried_notes_count: number;
  status: string;
  message: string;
}

/**
 * Lists all active private notes with sizes and timestamps.
 */
export async function listNotes(): Promise<NoteMetadataDTO[]> {
  return apiRequest<NoteMetadataDTO[]>('/memory/notebook/notes');
}

/**
 * Searches across notes bodies and titles for relevant snippets.
 */
export async function searchNotes(query: string): Promise<NoteSearchResultDTO[]> {
  return apiRequest<NoteSearchResultDTO[]>(
    `/memory/notebook/notes/search?q=${encodeURIComponent(query)}`
  );
}

/**
 * Reads the full markdown content of a private note.
 */
export async function getNote(title: string): Promise<NoteEntryDTO> {
  return apiRequest<NoteEntryDTO>(
    `/memory/notebook/notes/${encodeURIComponent(title)}`
  );
}

/**
 * Creates a note or appends content to an existing note.
 */
export async function appendNote(request: AppendNoteRequestDTO): Promise<NoteEntryDTO> {
  return apiRequest<NoteEntryDTO>('/memory/notebook/notes', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Atomically overwrites a note for human rectification or model refinement.
 */
export async function rewriteNote(
  title: string,
  request: RewriteNoteRequestDTO
): Promise<NoteEntryDTO> {
  return apiRequest<NoteEntryDTO>(
    `/memory/notebook/notes/${encodeURIComponent(title)}`,
    {
      method: 'PUT',
      body: JSON.stringify(request),
    }
  );
}

/**
 * Deletes a note file by title.
 */
export async function deleteNote(
  title: string
): Promise<{ status: string; deleted: boolean; title: string }> {
  return apiRequest<{ status: string; deleted: boolean; title: string }>(
    `/memory/notebook/notes/${encodeURIComponent(title)}`,
    {
      method: 'DELETE',
    }
  );
}

/**
 * Lists archived past context windows.
 */
export async function listContexts(): Promise<HistoryContextItemDTO[]> {
  return apiRequest<HistoryContextItemDTO[]>('/memory/notebook/history/contexts');
}

/**
 * Searches past execution history across all archived contexts.
 */
export async function searchHistory(
  query: string,
  maxResults = 10
): Promise<HistoryEntryItemDTO[]> {
  return apiRequest<HistoryEntryItemDTO[]>(
    `/memory/notebook/history/search?q=${encodeURIComponent(query)}&max_results=${maxResults}`
  );
}

/**
 * Smoothly switches to a clean context window while preserving notes and sandbox state.
 */
export async function switchToNewContext(
  request: NewContextRequestDTO
): Promise<NewContextResponseDTO> {
  return apiRequest<NewContextResponseDTO>('/memory/notebook/new-context', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}
