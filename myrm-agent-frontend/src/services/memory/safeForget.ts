/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: Frontend API client transport)
 *
 * [OUTPUT]
 * Safe Episodic Forget DTOs and API clients:
 * - probeMemoryParents: Probe competing parent tiers and session authorization
 * - executeSafeForget: Safely forget episodic memory with shared child retention guards
 * - getSafeForgetAuditEvents: Retrieve recorded after-commit invalidation events
 *
 * [POS]
 * Frontend API service for Item 149 SafeEpisodicForgetSuite.
 * Strict typing applied: 0 any types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface ParentProbeResponseDTO {
  memory_id: string;
  authorized: boolean;
  episodic_exists: boolean;
  competing_tiers: string[];
  has_competing_parents: boolean;
}

export interface SafeForgetRequestDTO {
  memory_id: string;
  caller_session_id: string;
  user_id?: string;
  allow_global?: boolean;
  reason?: string;
}

export interface SafeForgetResponseDTO {
  memory_id: string;
  deleted: boolean;
  unauthorized: boolean;
  retained_shared_children: boolean;
  deleted_child_tables: string[];
  message: string;
}

export interface SafeForgetAuditEventDTO {
  event_name: string;
  memory_id: string;
  tier: string;
  timestamp: number;
  reason: string;
  session_id: string;
}

/**
 * Probe competing parents and authorization status before forgetting an episodic memory.
 */
export async function probeMemoryParents(
  memoryId: string,
  callerSessionId: string,
  allowGlobal = true
): Promise<ParentProbeResponseDTO> {
  const query = new URLSearchParams({
    memory_id: memoryId,
    caller_session_id: callerSessionId,
    allow_global: String(allowGlobal),
  });
  return apiRequest<ParentProbeResponseDTO>(
    `/api/v1/memory/episodic-forget/probe?${query.toString()}`,
    {
      method: 'POST',
    }
  );
}

/**
 * Execute safe episodic forget under authorization and shared child retention semantics.
 */
export async function executeSafeForget(
  request: SafeForgetRequestDTO
): Promise<SafeForgetResponseDTO> {
  return apiRequest<SafeForgetResponseDTO>('/api/v1/memory/episodic-forget/execute', {
    method: 'POST',
    body: JSON.stringify(request),
    headers: {
      'Content-Type': 'application/json',
    },
  });
}

/**
 * Retrieve recorded after-commit invalidation audit events.
 */
export async function getSafeForgetAuditEvents(): Promise<SafeForgetAuditEventDTO[]> {
  return apiRequest<SafeForgetAuditEventDTO[]>('/api/v1/memory/episodic-forget/audit', {
    method: 'GET',
  });
}
