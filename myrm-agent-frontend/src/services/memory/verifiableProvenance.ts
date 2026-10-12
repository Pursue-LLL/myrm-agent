/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: Frontend API client transport)
 *
 * [OUTPUT]
 * Verifiable Provenance & Physical Isolation DTOs and API clients:
 * - generateVolumeToken: Request signed environment token for dedicated volume
 * - provePhysicalResidency: Transparent physical proof confirming storage residency
 * - purgePhysicalStorage: True physical multi-pass overwrite and destruction receipt
 * - inspectPiiContent: Active pre-ingest inspection shielding children identities, addresses, and financials
 *
 * [POS]
 * Frontend API service for Item 160 VerifiableMemoryProvenanceAndZeroCrossTenantPhysicalIsolationSuite.
 * Strict typing applied: 0 any types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface TenantSandboxContextDTO {
  tenant_id: string;
  sandbox_id: string;
  volume_id: string;
  environment_token: string;
}

export interface ResidencyProofRequest {
  file_path: string;
  context: TenantSandboxContextDTO;
  extra_metadata?: Record<string, string>;
}

export interface ResidencyProofResponse {
  tenant_id: string;
  sandbox_id: string;
  volume_id: string;
  storage_path: string;
  volume_mount_point: string;
  file_inode: number;
  content_sha256: string;
  is_exclusive_volume: boolean;
  verified_at: string;
  metadata: Record<string, string>;
}

export interface PhysicalPurgeRequest {
  file_path: string;
  context: TenantSandboxContextDTO;
}

export interface DestructionReceiptResponse {
  receipt_id: string;
  tenant_id: string;
  sandbox_id: string;
  volume_id: string;
  purged_storage_path: string;
  bytes_overwritten: number;
  overwrite_passes: number;
  status: string;
  destruction_digest: string;
  completed_at: string;
}

export interface InspectPiiRequest {
  text: string;
}

export interface PiiShieldResponse {
  intercepted: boolean;
  detected_categories: string[];
  sanitized_text: string;
  masked_spans: string[];
  has_child_privacy_violation: boolean;
}

export interface TokenGenerateRequest {
  tenant_id: string;
  sandbox_id: string;
  volume_id: string;
}

export interface TokenGenerateResponse {
  environment_token: string;
  tenant_id: string;
  sandbox_id: string;
  volume_id: string;
}

export async function generateVolumeToken(
  req: TokenGenerateRequest
): Promise<TokenGenerateResponse> {
  return apiRequest<TokenGenerateResponse>('/api/memory/provenance/token', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function provePhysicalResidency(
  req: ResidencyProofRequest
): Promise<ResidencyProofResponse> {
  return apiRequest<ResidencyProofResponse>('/api/memory/provenance/residency-proof', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function purgePhysicalStorage(
  req: PhysicalPurgeRequest
): Promise<DestructionReceiptResponse> {
  return apiRequest<DestructionReceiptResponse>('/api/memory/provenance/purge', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function inspectPiiContent(
  req: InspectPiiRequest
): Promise<PiiShieldResponse> {
  return apiRequest<PiiShieldResponse>('/api/memory/provenance/inspect-pii', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}
