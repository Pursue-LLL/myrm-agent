/**
 * [INPUT]
 * @/services/api::apiClient (POS: standard client facade)
 *
 * [OUTPUT]
 * Types and client functions for Item 101:
 * HumanReadableMarkdownBidiSyncAndMemoryCuratorStudioSuite.
 *
 * [POS]
 * Client layer connecting frontend command-center UI to FastAPI backend endpoints.
 * Strict typing applied: No `any` types allowed. Single file < 300 lines.
 */

import { apiClient } from '@/services/api';

export type CuratedMemoryCategory = 'preference' | 'fact' | 'procedure' | 'experience';
export type CuratedMemoryStatus = 'confirmed' | 'pending_confirmation' | 'rejected' | 'archived';

export interface CuratedMemoryEntryDTO {
  entry_id: string;
  category: CuratedMemoryCategory;
  title: string;
  content: string;
  confidence: number;
  status: CuratedMemoryStatus;
  tags: string[];
  source_session_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CurateEntryRequest {
  category: CuratedMemoryCategory;
  title: string;
  content: string;
  confidence?: number;
  status?: CuratedMemoryStatus;
  tags?: string[];
  source_session_id?: string | null;
}

export interface UpdateCurateEntryRequest {
  title?: string;
  content?: string;
  category?: CuratedMemoryCategory;
  status?: CuratedMemoryStatus;
  tags?: string[];
}

export interface AuditEntryRequest {
  is_approved: boolean;
}

export interface MarkdownSyncRequest {
  markdown_text: string;
  hard_delete?: boolean;
}

export interface MarkdownSyncResponseDTO {
  added_count: number;
  updated_count: number;
  deleted_count: number;
  added_entries: CuratedMemoryEntryDTO[];
  updated_entries: CuratedMemoryEntryDTO[];
  deleted_entry_ids: string[];
}

export interface CuratorStudioSummaryDTO {
  total_entries: number;
  confirmed_count: number;
  pending_count: number;
  rejected_count: number;
  archived_count: number;
  categories_breakdown: Record<string, number>;
}

export async function fetchCuratorEntries(
  category?: string,
  status?: string
): Promise<CuratedMemoryEntryDTO[]> {
  const params: Record<string, string> = {};
  if (category && category !== 'all') params.category = category;
  if (status && status !== 'all') params.status = status;
  return apiClient.get<CuratedMemoryEntryDTO[]>('/memory/curator/entries', { params });
}

export async function createCuratorEntry(
  request: CurateEntryRequest
): Promise<CuratedMemoryEntryDTO> {
  return apiClient.post<CuratedMemoryEntryDTO>('/memory/curator/entries', request);
}

export async function updateCuratorEntry(
  entryId: string,
  request: UpdateCurateEntryRequest
): Promise<CuratedMemoryEntryDTO> {
  return apiClient.put<CuratedMemoryEntryDTO>(`/memory/curator/entries/${entryId}`, request);
}

export async function auditCuratorEntry(
  entryId: string,
  isApproved: boolean
): Promise<CuratedMemoryEntryDTO> {
  return apiClient.post<CuratedMemoryEntryDTO>(`/memory/curator/entries/${entryId}/audit`, {
    is_approved: isApproved,
  });
}

export async function eraseCuratorEntry(
  entryId: string,
  hardErase: boolean = true
): Promise<{ is_success: boolean }> {
  return apiClient.delete<{ is_success: boolean }>(`/memory/curator/entries/${entryId}`, {
    params: { hard_erase: hardErase },
  });
}

export async function syncFromMarkdown(
  markdownText: string,
  hardDelete: boolean = false
): Promise<MarkdownSyncResponseDTO> {
  return apiClient.post<MarkdownSyncResponseDTO>('/memory/curator/sync', {
    markdown_text: markdownText,
    hard_delete: hardDelete,
  });
}

export async function fetchCuratorSummary(): Promise<CuratorStudioSummaryDTO> {
  return apiClient.get<CuratorStudioSummaryDTO>('/memory/curator/summary');
}

export async function exportCuratorMarkdown(
  title: string = 'Workspace Memory Mirror'
): Promise<string> {
  return apiClient.get<string>('/memory/curator/export', {
    params: { title },
  });
}
