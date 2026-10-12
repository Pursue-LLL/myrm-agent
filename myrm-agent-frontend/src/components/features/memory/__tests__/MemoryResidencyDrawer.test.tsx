/** @vitest-environment jsdom */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MemoryResidencyDrawer } from '../drawers/MemoryResidencyDrawer';
import * as provService from '@/services/memory/verifiableProvenance';

describe('MemoryResidencyDrawer Component', () => {
  const mockProof: provService.ResidencyProofResponse = {
    tenant_id: 'tenant-test-1',
    sandbox_id: 'sandbox-test-1',
    volume_id: 'vol-test-1',
    storage_path: '/data/sandbox/volumes/memory.db',
    volume_mount_point: '/data/sandbox/volumes',
    file_inode: 987654,
    content_sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    is_exclusive_volume: true,
    verified_at: '2026-10-12T08:00:00Z',
    metadata: { cluster: 'edge-01' },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(provService, 'generateVolumeToken').mockResolvedValue({
      environment_token: 'token-123',
      tenant_id: 'tenant-test-1',
      sandbox_id: 'sandbox-test-1',
      volume_id: 'vol-test-1',
    });
    vi.spyOn(provService, 'provePhysicalResidency').mockResolvedValue(mockProof);
  });

  it('renders nothing when closed', () => {
    const { container } = render(
      <MemoryResidencyDrawer isOpen={false} onClose={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders drawer header, tabs, and proof content when open', async () => {
    const handleClose = vi.fn();
    render(
      <MemoryResidencyDrawer
        isOpen={true}
        onClose={handleClose}
        tenantId="tenant-test-1"
        sandboxId="sandbox-test-1"
        volumeId="vol-test-1"
        storagePath="/data/sandbox/volumes/memory.db"
      />
    );

    expect(screen.getByText('存储物理驻留与合规控制台')).toBeInTheDocument();
    expect(screen.getByText('物理卷驻留凭证')).toBeInTheDocument();
    expect(screen.getByText('入库脱敏盾')).toBeInTheDocument();
    expect(screen.getByText('物理覆写销毁')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('专属无共享卷 (Fail-Closed)')).toBeInTheDocument();
    });

    const closeBtn = screen.getByLabelText('关闭控制台');
    await userEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('navigates to purge tab and requires PURGE confirmation', async () => {
    render(
      <MemoryResidencyDrawer
        isOpen={true}
        onClose={vi.fn()}
        tenantId="tenant-test-1"
        sandboxId="sandbox-test-1"
        volumeId="vol-test-1"
      />
    );

    const purgeTabBtn = screen.getByText('物理覆写销毁');
    await userEvent.click(purgeTabBtn);

    expect(
      screen.getByText('不可逆物理扇区级覆写 (DoD 5220.22-M)')
    ).toBeInTheDocument();

    const purgeActionBtn = screen.getByRole('button', { name: /确认彻底物理销毁/i });
    expect(purgeActionBtn).toBeDisabled();

    const input = screen.getByPlaceholderText('PURGE');
    await userEvent.type(input, 'PURGE');
    expect(purgeActionBtn).not.toBeDisabled();
  });

  it('navigates to pii shield tab and displays sandbox test input', async () => {
    render(
      <MemoryResidencyDrawer
        isOpen={true}
        onClose={vi.fn()}
      />
    );

    const shieldTabBtn = screen.getByText('入库脱敏盾');
    await userEvent.click(shieldTabBtn);

    expect(screen.getByText('Pre-Ingest PII 脱敏规则')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /执行脱敏审计/i })).toBeInTheDocument();
  });
});
