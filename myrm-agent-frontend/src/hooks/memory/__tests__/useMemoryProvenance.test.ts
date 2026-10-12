/**
 * [INPUT]
 * @/services/memory/verifiableProvenance (Mocked API client transport)
 *
 * [OUTPUT]
 * Comprehensive unit tests verifying useMemoryProvenance Hook behaviors:
 * - Default initialization state
 * - Token request execution
 * - Physical residency proof retrieval and state mutation
 * - Physical purge execution and receipt generation
 * - Pre-ingest PII shield inspection
 * - Fail-closed error handling
 *
 * [POS]
 * Frontend unit tests for Item 160 VerifiableMemoryProvenanceAndZeroCrossTenantPhysicalIsolationSuite.
 * Strict typing applied: 0 any types allowed.
 */

import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as provService from '@/services/memory/verifiableProvenance';
import { useMemoryProvenance } from '../useMemoryProvenance';

vi.mock('@/services/memory/verifiableProvenance', () => ({
  generateVolumeToken: vi.fn(),
  provePhysicalResidency: vi.fn(),
  purgePhysicalStorage: vi.fn(),
  inspectPiiContent: vi.fn(),
}));

describe('useMemoryProvenance', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockContext: provService.TenantSandboxContextDTO = {
    tenant_id: 'tenant-acme',
    sandbox_id: 'sb-prod-10',
    volume_id: 'vol-dedicated-10',
    environment_token: 'tok-signed-sha256-hex-digest-sample',
  };

  const mockProof: provService.ResidencyProofResponse = {
    tenant_id: 'tenant-acme',
    sandbox_id: 'sb-prod-10',
    volume_id: 'vol-dedicated-10',
    storage_path: '/volumes/vol-dedicated-10/memory.db',
    volume_mount_point: '/volumes/vol-dedicated-10',
    file_inode: 987654,
    content_sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    is_exclusive_volume: true,
    verified_at: '2026-10-12T12:00:00Z',
    metadata: { file_size_bytes: '4096' },
  };

  const mockReceipt: provService.DestructionReceiptResponse = {
    receipt_id: 'rcpt-purged-001',
    tenant_id: 'tenant-acme',
    sandbox_id: 'sb-prod-10',
    volume_id: 'vol-dedicated-10',
    purged_storage_path: '/volumes/vol-dedicated-10/memory.db',
    bytes_overwritten: 12288,
    overwrite_passes: 3,
    status: 'verified_destroyed',
    destruction_digest: 'ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb',
    completed_at: '2026-10-12T12:05:00Z',
  };

  const mockPii: provService.PiiShieldResponse = {
    intercepted: true,
    detected_categories: ['child_identity', 'precise_residential_address'],
    sanitized_text: 'User: My child is [REDACTED_CHILD_IDENTITY]',
    masked_spans: ['Alice'],
    has_child_privacy_violation: true,
  };

  it('initializes with clean default state', () => {
    const { result } = renderHook(() => useMemoryProvenance());

    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.proof).toBeNull();
    expect(result.current.latestReceipt).toBeNull();
    expect(result.current.piiInspection).toBeNull();
  });

  it('requests volume token successfully', async () => {
    vi.mocked(provService.generateVolumeToken).mockResolvedValueOnce({
      environment_token: 'generated-token-xyz',
      tenant_id: 'tenant-acme',
      sandbox_id: 'sb-prod-10',
      volume_id: 'vol-dedicated-10',
    });

    const { result } = renderHook(() => useMemoryProvenance());

    let token = '';
    await act(async () => {
      token = await result.current.requestVolumeToken(
        'tenant-acme',
        'sb-prod-10',
        'vol-dedicated-10'
      );
    });

    expect(token).toBe('generated-token-xyz');
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('fetches physical residency proof and updates state', async () => {
    vi.mocked(provService.provePhysicalResidency).mockResolvedValueOnce(mockProof);

    const { result } = renderHook(() => useMemoryProvenance());

    await act(async () => {
      await result.current.fetchResidencyProof({
        file_path: '/volumes/vol-dedicated-10/memory.db',
        context: mockContext,
      });
    });

    expect(result.current.proof).toEqual(mockProof);
    expect(result.current.proof?.is_exclusive_volume).toBe(true);
    expect(result.current.loading).toBe(false);
  });

  it('executes physical purge and stores destruction receipt', async () => {
    vi.mocked(provService.purgePhysicalStorage).mockResolvedValueOnce(mockReceipt);

    const { result } = renderHook(() => useMemoryProvenance());

    await act(async () => {
      await result.current.executePhysicalPurge({
        file_path: '/volumes/vol-dedicated-10/memory.db',
        context: mockContext,
      });
    });

    expect(result.current.latestReceipt).toEqual(mockReceipt);
    expect(result.current.latestReceipt?.status).toBe('verified_destroyed');
    expect(result.current.loading).toBe(false);
  });

  it('scans text and updates pii inspection state', async () => {
    vi.mocked(provService.inspectPiiContent).mockResolvedValueOnce(mockPii);

    const { result } = renderHook(() => useMemoryProvenance());

    await act(async () => {
      await result.current.scanPii('Sensitive string with child name');
    });

    expect(result.current.piiInspection).toEqual(mockPii);
    expect(result.current.piiInspection?.has_child_privacy_violation).toBe(true);
  });

  it('handles fail-closed errors and updates error state', async () => {
    vi.mocked(provService.provePhysicalResidency).mockRejectedValueOnce(
      new Error('Fail-Closed security rejection: Missing context')
    );

    const { result } = renderHook(() => useMemoryProvenance());

    await act(async () => {
      await expect(
        result.current.fetchResidencyProof({
          file_path: '/prohibited/shared.db',
          context: mockContext,
        })
      ).rejects.toThrow('Fail-Closed security rejection');
    });

    expect(result.current.error).toBe(
      'Fail-Closed security rejection: Missing context'
    );
    expect(result.current.loading).toBe(false);
  });
});
