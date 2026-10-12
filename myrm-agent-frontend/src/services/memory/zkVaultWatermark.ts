/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: Frontend API client transport)
 *
 * [OUTPUT]
 * Zero Knowledge Memory Vault DTOs and API clients:
 * - sealMemory: Envelope encrypt memory item using local master passphrase
 * - unsealMemory: Decrypt memory item using passphrase
 * - listVaultMemories: Fetch unsealed memory items optionally filtered by tier
 * - exportDistilledPackage: Distill memories and embed invisible provenance watermark
 * - verifyWatermark: Extract and verify provenance watermark from leaked text
 * - verifySandboxResidency: Check runtime hardware and volume binding
 * - unlockSandboxResidency: Unlock hardware binding and rebind to new instance
 *
 * [POS]
 * Frontend API service for Item 159 ZeroKnowledgeMemoryVaultAndAntiCloningProvenanceWatermarkingSuite.
 * Strict typing applied: 0 any types allowed.
 */

import { apiRequest } from '@/lib/api';

export type MemorySensitivityTier =
  | 'public_sharable'
  | 'team_internal'
  | 'strictly_private_pii';

export interface EncryptedEnvelopeDTO {
  ciphertext_hex: string;
  iv_hex: string;
  salt_hex: string;
  encrypted_dek_hex: string;
  algorithm: string;
  created_at: string;
}

export interface ProvenanceWatermarkDTO {
  tenant_id: string;
  user_id: string;
  timestamp_iso: string;
  signature: string;
}

export interface DistilledMemoryItemDTO {
  memory_id: string;
  content: string;
  sensitivity_tier: MemorySensitivityTier;
  category: string;
  redacted: boolean;
}

export interface DistilledExportPackageDTO {
  tenant_id: string;
  target_tier: MemorySensitivityTier;
  exported_at: string;
  items: DistilledMemoryItemDTO[];
  watermarked_text: string;
  watermark_signature: string;
}

export interface SealMemoryRequest {
  memory_id: string;
  content: string;
  sensitivity_tier?: MemorySensitivityTier;
  category?: string;
  passphrase: string;
}

export interface UnsealMemoryRequest {
  memory_id: string;
  passphrase: string;
}

export interface ExportDistilledRequest {
  tenant_id: string;
  user_id: string;
  target_tier?: MemorySensitivityTier;
  redact_pii?: boolean;
  timestamp_iso?: string;
}

export interface VerifyWatermarkRequest {
  exported_text: string;
}

export interface VerifyResidencyRequest {
  instance_guid: string;
  volume_id: string;
  tenant_id: string;
}

export interface UnlockResidencyRequest {
  provided_passphrase: string;
  expected_passphrase: string;
  new_instance_guid: string;
  new_volume_id: string;
  tenant_id: string;
}

export interface ResidencyCheckResponse {
  allowed: boolean;
  diagnostic: string;
}

export async function sealMemory(
  req: SealMemoryRequest
): Promise<EncryptedEnvelopeDTO> {
  return apiRequest<EncryptedEnvelopeDTO>('/api/memory/zk-vault/seal', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function unsealMemory(
  req: UnsealMemoryRequest
): Promise<DistilledMemoryItemDTO> {
  return apiRequest<DistilledMemoryItemDTO>('/api/memory/zk-vault/unseal', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function listVaultMemories(
  tier?: MemorySensitivityTier
): Promise<DistilledMemoryItemDTO[]> {
  const url = tier
    ? `/api/memory/zk-vault/memories?tier=${encodeURIComponent(tier)}`
    : '/api/memory/zk-vault/memories';
  return apiRequest<DistilledMemoryItemDTO[]>(url, { method: 'GET' });
}

export async function exportDistilledPackage(
  req: ExportDistilledRequest
): Promise<DistilledExportPackageDTO> {
  return apiRequest<DistilledExportPackageDTO>('/api/memory/zk-vault/export', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function verifyWatermark(
  req: VerifyWatermarkRequest
): Promise<ProvenanceWatermarkDTO> {
  return apiRequest<ProvenanceWatermarkDTO>('/api/memory/zk-vault/verify-watermark', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function verifySandboxResidency(
  req: VerifyResidencyRequest
): Promise<ResidencyCheckResponse> {
  return apiRequest<ResidencyCheckResponse>('/api/memory/zk-vault/verify-residency', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function unlockSandboxResidency(
  req: UnlockResidencyRequest
): Promise<{ unlocked: boolean }> {
  return apiRequest<{ unlocked: boolean }>('/api/memory/zk-vault/unlock-residency', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}
