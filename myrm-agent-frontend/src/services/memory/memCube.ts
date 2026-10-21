/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Types: CubeScopeType, CubeRecordDTO, MemoryCubeDTO, CreateCubeRequestDTO,
 *        MountPolicyDTO, SetMountPolicyRequestDTO, CubeQueryRequestDTO,
 *        CubeQueryResultDTO, CubeWriteRequestDTO, CubeWriteResultDTO,
 *        CubeMatrixOverviewDTO
 * Functions: getCubeMatrixOverview, listMemoryCubes, createMemoryCube,
 *            listCubeRecords, getAgentMountPolicy, setAgentMountPolicy,
 *            queryCubesFederated, writeCubeMemory
 *
 * [POS]
 * Client API service for Item 124 Memory Cube Scoped Isolation & Dynamic Mounting Suite.
 * Strict typing applied: No `any` types allowed. Single file < 200 lines.
 */

import { apiRequest } from '@/lib/api';

export type CubeScopeType = 'global_shared' | 'project_workspace' | 'agent_private' | 'ephemeral_task';

export interface CubeRecordDTO {
  record_id: string;
  cube_id: string;
  content: string;
  metadata: Record<string, string | number | boolean>;
  created_at: number;
}

export interface MemoryCubeDTO {
  cube_id: string;
  name: string;
  scope_type: CubeScopeType;
  owner_id?: string | null;
  description: string;
  is_read_only: boolean;
  item_count: number;
  created_at: number;
  updated_at: number;
}

export interface CreateCubeRequestDTO {
  cube_id?: string;
  name: string;
  scope_type: CubeScopeType;
  owner_id?: string | null;
  description?: string;
  is_read_only?: boolean;
}

export interface MountPolicyDTO {
  agent_id: string;
  readable_cube_ids: string[];
  writable_cube_ids: string[];
  default_write_cube_id?: string | null;
  strict_isolation: boolean;
}

export interface SetMountPolicyRequestDTO {
  readable_cube_ids: string[];
  writable_cube_ids: string[];
  default_write_cube_id?: string | null;
  strict_isolation: boolean;
}

export interface CubeQueryRequestDTO {
  agent_id: string;
  query: string;
  explicit_cube_ids?: string[];
  limit?: number;
}

export interface CubeQueryResultDTO {
  items: CubeRecordDTO[];
  total_found: number;
  queried_cube_ids: string[];
  query_duration_ms: number;
}

export interface CubeWriteRequestDTO {
  agent_id: string;
  content: string;
  target_cube_id?: string | null;
  metadata?: Record<string, string | number | boolean>;
}

export interface CubeWriteResultDTO {
  success: boolean;
  record?: CubeRecordDTO | null;
  destination_cube_id?: string | null;
  rejection_reason?: string | null;
}

export interface CubeMatrixOverviewDTO {
  cubes: MemoryCubeDTO[];
  policies: MountPolicyDTO[];
  total_cubes: number;
  total_records: number;
  system_healthy: boolean;
}

export async function getCubeMatrixOverview(): Promise<CubeMatrixOverviewDTO> {
  return apiRequest<CubeMatrixOverviewDTO>('/memory/cubes/matrix/overview', { method: 'GET' });
}

export async function listMemoryCubes(): Promise<MemoryCubeDTO[]> {
  return apiRequest<MemoryCubeDTO[]>('/memory/cubes', { method: 'GET' });
}

export async function createMemoryCube(payload: CreateCubeRequestDTO): Promise<MemoryCubeDTO> {
  return apiRequest<MemoryCubeDTO>('/memory/cubes', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function listCubeRecords(cubeId: string): Promise<CubeRecordDTO[]> {
  return apiRequest<CubeRecordDTO[]>(`/memory/cubes/records/${cubeId}`, { method: 'GET' });
}

export async function getAgentMountPolicy(agentId: string): Promise<MountPolicyDTO> {
  return apiRequest<MountPolicyDTO>(`/memory/cubes/mount/${agentId}`, { method: 'GET' });
}

export async function setAgentMountPolicy(agentId: string, payload: SetMountPolicyRequestDTO): Promise<MountPolicyDTO> {
  return apiRequest<MountPolicyDTO>(`/memory/cubes/mount/${agentId}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function queryCubesFederated(payload: CubeQueryRequestDTO): Promise<CubeQueryResultDTO> {
  return apiRequest<CubeQueryResultDTO>('/memory/cubes/query', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function writeCubeMemory(payload: CubeWriteRequestDTO): Promise<CubeWriteResultDTO> {
  return apiRequest<CubeWriteResultDTO>('/memory/cubes/write', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
