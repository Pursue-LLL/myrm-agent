/** @vitest-environment jsdom */

/**
 * Test suite verifying Item 145 MempalaceInodeIdentity:
 * 1. Default render of Inode identity inspection card with header and scenario tabs.
 * 2. Evaluating directory sync identity with mocked inodeIdentityApi response.
 * 3. Switching between exact_match, moved_or_renamed, inode_reused, and brand_new scenarios.
 * 4. Displaying relocation warning banner when directory move/rename is detected.
 * 5. Testing graceful local fallback when service fails.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { InodeIdentityInspectionCard } from '../command-center/InodeIdentityInspectionCard';
import type { VerifySyncRequest, VerifySyncResponse } from '@/services/memory/inodeIdentity';

const { mockVerifySync, mockResolveIdentity, mockGetHealth } = vi.hoisted(() => ({
  mockVerifySync: vi.fn(),
  mockResolveIdentity: vi.fn(),
  mockGetHealth: vi.fn(),
}));

vi.mock('@/services/memory/inodeIdentity', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    inodeIdentityApi: {
      verifySync: mockVerifySync,
      resolveIdentity: mockResolveIdentity,
      getHealth: mockGetHealth.mockResolvedValue({ status: 'ok', module: 'inode_identity', version: '1.0.0' }),
    },
  };
});

describe('InodeIdentityInspectionCard (Item 145 P0)', () => {
  const sampleExactDecision: VerifySyncResponse = {
    action: 'proceed_incremental',
    match_kind: 'exact_match',
    reason: 'Exact physical identity and canonical path match',
    old_path: '/Users/workspace/projects/vortexai',
    new_path: '/Users/workspace/projects/vortexai',
    physical_key: '16777220:86241920',
    needs_database_relocation: false,
    identity: {
      canonical_path: '/Users/workspace/projects/vortexai',
      device_id: 16777220,
      inode_id: 86241920,
      birth_time_ns: 1728000000000000,
      root_signature: 'auto:c89e1a3b4f',
      fs_kind: 'posix',
      is_symlink: false,
      physical_key: '16777220:86241920',
    },
  };

  const sampleMoveDecision: VerifySyncResponse = {
    action: 'relocate_and_proceed',
    match_kind: 'moved_or_renamed',
    reason: "Directory moved or renamed from '/Users/workspace/projects/vortexai' to '/Users/workspace/projects/vortexai-renamed'.",
    old_path: '/Users/workspace/projects/vortexai',
    new_path: '/Users/workspace/projects/vortexai-renamed',
    physical_key: '16777220:86241920',
    needs_database_relocation: true,
    identity: {
      canonical_path: '/Users/workspace/projects/vortexai-renamed',
      device_id: 16777220,
      inode_id: 86241920,
      birth_time_ns: 1728000000000000,
      root_signature: 'auto:c89e1a3b4f',
      fs_kind: 'posix',
      is_symlink: false,
      physical_key: '16777220:86241920',
    },
  };

  const sampleRebuildDecision: VerifySyncResponse = {
    action: 'rebuild_warning',
    match_kind: 'inode_reused',
    reason: 'Path has new physical identity. Rebuild detected.',
    old_path: '/Users/workspace/projects/vortexai',
    new_path: '/Users/workspace/projects/vortexai',
    physical_key: '16777220:86241920',
    needs_database_relocation: false,
    identity: {
      canonical_path: '/Users/workspace/projects/vortexai',
      device_id: 16777220,
      inode_id: 86241920,
      birth_time_ns: 1728000000000000,
      root_signature: 'auto:c89e1a3b4f',
      fs_kind: 'posix',
      is_symlink: false,
      physical_key: '16777220:86241920',
    },
  };

  const sampleBrandNewDecision: VerifySyncResponse = {
    action: 'register_new',
    match_kind: 'brand_new',
    reason: 'Unrecognized workspace directory.',
    old_path: null,
    new_path: '/Users/workspace/new-client-app',
    physical_key: '16777220:86242944',
    needs_database_relocation: false,
    identity: {
      canonical_path: '/Users/workspace/new-client-app',
      device_id: 16777220,
      inode_id: 86242944,
      birth_time_ns: 1728000000000000,
      root_signature: 'auto:brand_new_99',
      fs_kind: 'posix',
      is_symlink: false,
      physical_key: '16777220:86242944',
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockVerifySync.mockImplementation(async (req: VerifySyncRequest) => {
      if (req.target_path.includes('renamed')) {
        return sampleMoveDecision;
      }
      if (req.known_identities.some((k) => k.inode_id > 86241920)) {
        return sampleRebuildDecision;
      }
      if (req.target_path.includes('new-client-app')) {
        return sampleBrandNewDecision;
      }
      return sampleExactDecision;
    });
  });

  it('renders header, title, and scenario tabs correctly', async () => {
    render(<InodeIdentityInspectionCard />);

    expect(screen.getByText('Sync 目录 Inode 身份守卫')).toBeInTheDocument();
    expect(screen.getByText(/Item 145 · P0/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '日常增量同步' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '目录重命名/移动' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重建/换卷预警' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '全新工作区' })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/精确物理匹配 \(Exact Match\)/)).toBeInTheDocument();
      expect(screen.getByText('PROCEED_INCREMENTAL')).toBeInTheDocument();
    });
  });

  it('switches to moved_or_renamed scenario and shows relocation banner', async () => {
    render(<InodeIdentityInspectionCard />);

    const moveBtn = screen.getByRole('button', { name: '目录重命名/移动' });
    fireEvent.click(moveBtn);

    await waitFor(() => {
      expect(screen.getByText(/重命名迁移感知 \(Move Detected\)/)).toBeInTheDocument();
      expect(screen.getByText(/检测到目录重命名\/移动，正在原子重定向数据库工作区指针/)).toBeInTheDocument();
      expect(screen.getByText('RELOCATE_AND_PROCEED')).toBeInTheDocument();
    });
  });

  it('switches to rebuild_warning scenario correctly', async () => {
    render(<InodeIdentityInspectionCard />);

    const rebuildBtn = screen.getByRole('button', { name: '重建/换卷预警' });
    fireEvent.click(rebuildBtn);

    await waitFor(() => {
      expect(screen.getByText(/重建\/换卷预警 \(Rebuild Warning\)/)).toBeInTheDocument();
      expect(screen.getByText('REBUILD_WARNING')).toBeInTheDocument();
    });
  });

  it('switches to brand_new scenario correctly', async () => {
    render(<InodeIdentityInspectionCard />);

    const newBtn = screen.getByRole('button', { name: '全新工作区' });
    fireEvent.click(newBtn);

    await waitFor(() => {
      expect(screen.getByText(/全新工作区 \(Brand New\)/)).toBeInTheDocument();
      expect(screen.getByText('REGISTER_NEW')).toBeInTheDocument();
    });
  });

  it('falls back gracefully to offline simulation when API errors', async () => {
    mockVerifySync.mockRejectedValue(new Error('Network offline'));

    render(<InodeIdentityInspectionCard />);

    await waitFor(() => {
      expect(screen.getByText(/精确物理匹配 \(Exact Match\)/)).toBeInTheDocument();
      expect(screen.getByText('PROCEED_INCREMENTAL')).toBeInTheDocument();
    });
  });
});
