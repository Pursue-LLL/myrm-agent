/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: Frontend API client transport)
 *
 * [OUTPUT]
 * Project Context USB Dongle DTOs and API clients:
 * - initProjectDongle: Initialize 4-tier markdown memory files
 * - getDongleState: Fetch state and bullet blocks across tiers
 * - getDonglePromptContext: Retrieve rendered Layer 1 relay prompt
 * - syncDongleBlocks: Synchronize and persist bullet blocks with spill handling
 *
 * [POS]
 * Frontend API service for Item 152 ProjectContextUsbDongleAndCrossAgentRelaySuite.
 * Strict typing applied: 0 any types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface DongleBlockDTO {
  block_id: string;
  block_type: string;
  content: string;
  created_date: string;
  status?: string;
  tags?: string[];
}

export interface DongleArchivePointerDTO {
  block_id: string;
  date_str: string;
  summary: string;
  target_archive_file: string;
}

export interface DongleStateDTO {
  workspace_dir: string;
  project_state_blocks: DongleBlockDTO[];
  decision_blocks: DongleBlockDTO[];
  lesson_blocks: DongleBlockDTO[];
  index_content: string;
  archive_pointers: DongleArchivePointerDTO[];
  total_active_blocks: number;
}

export interface DongleInitRequestDTO {
  workspace_dir: string;
}

export interface DongleInitResponseDTO {
  workspace_dir: string;
  initialized_files: string[];
  message: string;
}

export interface DongleSyncRequestDTO {
  workspace_dir: string;
  blocks: DongleBlockDTO[];
}

export interface DongleSyncResponseDTO {
  updated_files: string[];
  added_blocks_count: number;
  spilled_blocks_count: number;
  created_pointers: DongleArchivePointerDTO[];
  message: string;
}

export interface DongleContextPromptResponseDTO {
  workspace_dir: string;
  prompt_context: string;
}

export async function initProjectDongle(
  payload: DongleInitRequestDTO,
): Promise<DongleInitResponseDTO> {
  return apiRequest<DongleInitResponseDTO>('/api/memory/dongle/init', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getDongleState(
  workspaceDir: string,
): Promise<DongleStateDTO> {
  const query = new URLSearchParams({ workspace_dir: workspaceDir });
  return apiRequest<DongleStateDTO>(`/api/memory/dongle/state?${query.toString()}`, {
    method: 'GET',
  });
}

export async function getDonglePromptContext(
  workspaceDir: string,
): Promise<DongleContextPromptResponseDTO> {
  const query = new URLSearchParams({ workspace_dir: workspaceDir });
  return apiRequest<DongleContextPromptResponseDTO>(`/api/memory/dongle/prompt?${query.toString()}`, {
    method: 'GET',
  });
}

export async function syncDongleBlocks(
  payload: DongleSyncRequestDTO,
): Promise<DongleSyncResponseDTO> {
  return apiRequest<DongleSyncResponseDTO>('/api/memory/dongle/sync', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
