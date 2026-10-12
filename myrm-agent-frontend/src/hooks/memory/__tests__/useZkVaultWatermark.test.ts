import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as vaultService from '@/services/memory/zkVaultWatermark';
import { useZkVaultWatermark } from '../useZkVaultWatermark';

vi.mock('@/services/memory/zkVaultWatermark', () => ({
  sealMemory: vi.fn(),
  unsealMemory: vi.fn(),
  listVaultMemories: vi.fn(),
  exportDistilledPackage: vi.fn(),
  verifyWatermark: vi.fn(),
  verifySandboxResidency: vi.fn(),
  unlockSandboxResidency: vi.fn(),
}));

describe('useZkVaultWatermark', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockItem: vaultService.DistilledMemoryItemDTO = {
    memory_id: 'sec_mem_01',
    content: 'Corporate cloud infra access tokens',
    sensitivity_tier: 'team_internal',
    category: 'credentials',
    redacted: false,
  };

  const mockEnvelope: vaultService.EncryptedEnvelopeDTO = {
    ciphertext_hex: 'a1b2c3d4e5f6',
    iv_hex: '010203040506',
    salt_hex: 'aabbccddeeff',
    encrypted_dek_hex: '112233445566',
    algorithm: 'AES-256-GCM-Simulated-HMAC',
    created_at: '2026-10-10T10:00:00Z',
  };

  const mockPackage: vaultService.DistilledExportPackageDTO = {
    tenant_id: 'tenant_omega_01',
    target_tier: 'team_internal',
    exported_at: '2026-10-10T12:00:00Z',
    items: [mockItem],
    watermarked_text: 'Document header\u200d\u200b\u200c\u200d\nContent body',
    watermark_signature: 'sig_abc12345',
  };

  const mockWatermark: vaultService.ProvenanceWatermarkDTO = {
    tenant_id: 'tenant_omega_01',
    user_id: 'user_admin_09',
    timestamp_iso: '2026-10-10T12:00:00Z',
    signature: 'sig_abc12345',
  };

  it('initializes with default clean state', () => {
    const { result } = renderHook(() => useZkVaultWatermark());

    expect(result.current.isLoading).toBe(false);
    expect(result.current.isVerifying).toBe(false);
    expect(result.current.memories).toEqual([]);
    expect(result.current.lastExportPackage).toBeNull();
    expect(result.current.lastVerifiedWatermark).toBeNull();
    expect(result.current.residencyStatus).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('fetches memories and seals a new memory item', async () => {
    vi.mocked(vaultService.listVaultMemories).mockResolvedValueOnce([mockItem]);

    const { result } = renderHook(() => useZkVaultWatermark());

    let fetched: vaultService.DistilledMemoryItemDTO[] = [];
    await act(async () => {
      fetched = await result.current.fetchMemories('team_internal');
    });

    expect(fetched).toEqual([mockItem]);
    expect(result.current.memories).toEqual([mockItem]);

    // Seal new memory
    vi.mocked(vaultService.sealMemory).mockResolvedValueOnce(mockEnvelope);
    vi.mocked(vaultService.listVaultMemories).mockResolvedValueOnce([mockItem]);

    let envelope: vaultService.EncryptedEnvelopeDTO | null = null;
    await act(async () => {
      envelope = await result.current.seal({
        memory_id: 'sec_mem_02',
        content: 'New secret rule',
        passphrase: 'super_passphrase',
      });
    });

    expect(envelope).toEqual(mockEnvelope);
  });

  it('unseals an encrypted memory successfully', async () => {
    vi.mocked(vaultService.unsealMemory).mockResolvedValueOnce(mockItem);

    const { result } = renderHook(() => useZkVaultWatermark());

    let unsealed: vaultService.DistilledMemoryItemDTO | null = null;
    await act(async () => {
      unsealed = await result.current.unseal({
        memory_id: 'sec_mem_01',
        passphrase: 'super_passphrase',
      });
    });

    expect(unsealed).toEqual(mockItem);
    expect(result.current.memories).toContainEqual(mockItem);
  });

  it('exports distilled package with watermark and inspects watermark', async () => {
    vi.mocked(vaultService.exportDistilledPackage).mockResolvedValueOnce(mockPackage);
    vi.mocked(vaultService.verifyWatermark).mockResolvedValueOnce(mockWatermark);

    const { result } = renderHook(() => useZkVaultWatermark());

    let pkg: vaultService.DistilledExportPackageDTO | null = null;
    await act(async () => {
      pkg = await result.current.exportPackage({
        tenant_id: 'tenant_omega_01',
        user_id: 'user_admin_09',
        target_tier: 'team_internal',
      });
    });

    expect(pkg).toEqual(mockPackage);
    expect(result.current.lastExportPackage).toEqual(mockPackage);

    // Inspect watermark
    let wm: vaultService.ProvenanceWatermarkDTO | null = null;
    await act(async () => {
      wm = await result.current.inspectWatermark(mockPackage.watermarked_text);
    });

    expect(wm).toEqual(mockWatermark);
    expect(result.current.lastVerifiedWatermark).toEqual(mockWatermark);
  });

  it('checks sandbox residency and unlocks foreign migration', async () => {
    const mockResidency: vaultService.ResidencyCheckResponse = {
      allowed: true,
      diagnostic: 'Residency verified on current sandbox node.',
    };
    vi.mocked(vaultService.verifySandboxResidency).mockResolvedValueOnce(mockResidency);

    const { result } = renderHook(() => useZkVaultWatermark());

    let status: vaultService.ResidencyCheckResponse | null = null;
    await act(async () => {
      status = await result.current.checkResidency({
        instance_guid: 'inst_node_01',
        volume_id: 'vol_nvme_99',
        tenant_id: 'tenant_omega_01',
      });
    });

    expect(status).toEqual(mockResidency);
    expect(result.current.residencyStatus).toEqual(mockResidency);

    // Unlock residency
    vi.mocked(vaultService.unlockSandboxResidency).mockResolvedValueOnce({ unlocked: true });

    let unlocked = false;
    await act(async () => {
      unlocked = await result.current.unlockResidency({
        provided_passphrase: 'admin_pwd',
        expected_passphrase: 'admin_pwd',
        new_instance_guid: 'inst_node_02',
        new_volume_id: 'vol_nvme_99',
        tenant_id: 'tenant_omega_01',
      });
    });

    expect(unlocked).toBe(true);
    expect(result.current.residencyStatus?.allowed).toBe(true);
  });
});
