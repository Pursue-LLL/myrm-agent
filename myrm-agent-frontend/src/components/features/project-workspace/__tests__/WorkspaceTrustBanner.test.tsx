import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { WorkspaceTrustBanner } from '../WorkspaceTrustBanner';
import * as workspaceTrustService from '@/services/workspaceTrust';

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: string[]) => args.filter(Boolean).join(' '),
}));

vi.mock('@/lib/directoryBrowseRecent', () => ({
  shortenHomePath: (p: string) => p,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: vi.fn(),
}));

describe('WorkspaceTrustBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when workspacePath is null', () => {
    const { container } = render(<WorkspaceTrustBanner workspacePath={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when workspace is clean (requires_trust is false)', async () => {
    vi.spyOn(workspaceTrustService, 'previewWorkspaceTrustManifest').mockResolvedValueOnce({
      path: '/tmp/clean',
      canonical_path: '/tmp/clean',
      skill_count: 0,
      rule_count: 0,
      mcp_count: 0,
      plugin_count: 0,
      repo_command_prefixes: [],
      has_myrm_config: false,
      current_level: 'TRUSTED',
      requires_trust: false,
    });

    const { container } = render(<WorkspaceTrustBanner workspacePath="/tmp/clean" />);
    await waitFor(() => {
      expect(container.firstChild).toBeNull();
    });
  });

  it('renders restricted warning when workspace is restricted with isolated resources', async () => {
    vi.spyOn(workspaceTrustService, 'previewWorkspaceTrustManifest').mockResolvedValueOnce({
      path: '/tmp/repo',
      canonical_path: '/tmp/repo',
      skill_count: 2,
      rule_count: 1,
      mcp_count: 1,
      plugin_count: 0,
      repo_command_prefixes: [],
      has_myrm_config: false,
      current_level: 'RESTRICTED',
      requires_trust: true,
    });

    render(<WorkspaceTrustBanner workspacePath="/tmp/repo" />);

    await waitFor(() => {
      expect(screen.getByText('Restricted Mode')).toBeTruthy();
    });
    expect(screen.getByText('Trust Folder')).toBeTruthy();
    expect(screen.getByText(/3 isolated/i)).toBeTruthy();
  });

  it('trusts folder on click and notifies caller', async () => {
    const onTrustChanged = vi.fn();
    vi.spyOn(workspaceTrustService, 'previewWorkspaceTrustManifest').mockResolvedValue({
      path: '/tmp/repo',
      canonical_path: '/tmp/repo',
      skill_count: 1,
      rule_count: 0,
      repo_command_prefixes: [],
      has_myrm_config: false,
      current_level: 'RESTRICTED',
      requires_trust: true,
    });
    const decideSpy = vi.spyOn(workspaceTrustService, 'decideWorkspaceTrust').mockResolvedValueOnce({
      path: '/tmp/repo',
      level: 'TRUSTED',
      decided_at: '2026-09-27T00:00:00Z',
      manifest_hash: '123',
    });

    render(<WorkspaceTrustBanner workspacePath="/tmp/repo" onTrustChanged={onTrustChanged} />);

    await waitFor(() => {
      expect(screen.getByText('Restricted Mode')).toBeTruthy();
    });

    const trustBtn = screen.getByRole('button', { name: /trust folder/i });
    fireEvent.click(trustBtn);

    await waitFor(() => {
      expect(decideSpy).toHaveBeenCalledWith('/tmp/repo', 'TRUSTED');
      expect(onTrustChanged).toHaveBeenCalledWith('TRUSTED');
    });
  });
});
