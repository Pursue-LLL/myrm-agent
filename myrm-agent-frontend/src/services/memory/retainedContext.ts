/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Integration retained context auditing, purge, and provenance revocation DTOs & API clients:
 * - getRetainedContextSummary
 * - disconnectWithPurge
 * - listProvenanceRevocationRecords
 * - reinstateProvenance
 *
 * [POS]
 * Frontend API service for connector-scoped context retention governance (Topic 01 Item 179).
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface RetainedContextSummaryDTO {
  integration_id: string;
  provider_type: string;
  retained_memory_count: number;
  retained_tree_count: number;
  retained_fact_count: number;
  total_retained_items: number;
  oldest_retained_at: string | null;
  latest_retained_at: string | null;
  sample_snippets: string[];
  is_provenance_revoked: boolean;
}

export interface DisconnectWithPurgeRequestDTO {
  purge_mode: 'retain_context' | 'selective_purge' | 'purge_and_revoke';
  confirm_purge: boolean;
  reason?: string;
}

export interface DisconnectWithPurgeResponseDTO {
  integration_id: string;
  provider_type: string;
  disconnected: boolean;
  purged_items: number;
  mode: string;
  revocation_id: string | null;
  message: string;
  completed_at: string;
}

export interface ProvenanceRevocationAuditItemDTO {
  revocation_id: string;
  integration_id: string;
  reason: string;
  revoked_at: string;
  purged_items_count: number;
  actor: string;
}

/**
 * Audit and summarize retained context items associated with an external connector.
 */
export async function getRetainedContextSummary(
  integrationId: string,
  providerType = 'external_integration',
): Promise<RetainedContextSummaryDTO> {
  return apiRequest<RetainedContextSummaryDTO>(
    `/integrations/retained-context/summary/${encodeURIComponent(integrationId)}?provider_type=${encodeURIComponent(providerType)}`,
    {
      method: 'GET',
    },
  );
}

/**
 * Execute connector disconnect with selectable retention: preserve or purge & revoke.
 */
export async function disconnectWithPurge(
  integrationId: string,
  payload: DisconnectWithPurgeRequestDTO,
  providerType = 'external_integration',
  actor = 'user',
): Promise<DisconnectWithPurgeResponseDTO> {
  return apiRequest<DisconnectWithPurgeResponseDTO>(
    `/integrations/retained-context/disconnect-with-purge/${encodeURIComponent(integrationId)}?provider_type=${encodeURIComponent(providerType)}&actor=${encodeURIComponent(actor)}`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

/**
 * Retrieve historical provenance revocation audit records for compliance and traceability.
 */
export async function listProvenanceRevocationRecords(): Promise<
  ProvenanceRevocationAuditItemDTO[]
> {
  return apiRequest<ProvenanceRevocationAuditItemDTO[]>(
    '/integrations/retained-context/revocations',
    {
      method: 'GET',
    },
  );
}

/**
 * Reinstate a previously revoked integration provenance anchor upon re-authentication.
 */
export async function reinstateProvenance(
  integrationId: string,
): Promise<{ integration_id: string; reinstated: boolean }> {
  return apiRequest<{ integration_id: string; reinstated: boolean }>(
    `/integrations/retained-context/reinstate/${encodeURIComponent(integrationId)}`,
    {
      method: 'POST',
    },
  );
}
