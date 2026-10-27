import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { WorkspaceTrustBanner } from '../WorkspaceTrustBanner';
import * as workspaceTrustService from '@/services/workspaceTrust';
import { toast } from '@/hooks/shared/useToast';

// Echo the interpolation values too, so counts and paths are asserted along with the keys.
const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key}:${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: string[]) => args.filter(Boolean).join(' '),
}));

vi.mock('@/lib/directoryBrowseRecent', () => ({
  shortenHomePath: (p: string) => p,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: vi.fn(),
}));

function manifest(overrides: Partial<workspaceTrustService.WorkspaceTrustManifest> = {}) {
  return {
    path: '/tmp/repo',
    canonical_path: '/tmp/repo',
    skill_count: 0,
    rule_count: 0,
    mcp_count: 0,
    plugin_count: 0,
    repo_command_prefixes: [],
    pending_command_prefixes: [],
    has_myrm_config: false,
    current_level: 'RESTRICTED' as const,
    requires_trust: true,
    manifest_hash: 'hash-1',
    ...overrides,
  };
}

const entry = {
  path: '/tmp/repo',
  level: 'TRUSTED' as const,
  decided_at: '2026-09-27T00:00:00Z',
  manifest_hash: 'hash-1',
};

describe('WorkspaceTrustBanner', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.mocked(toast).mockClear();
  });

  it('renders nothing when workspacePath is null', () => {
    const { container } = render(<WorkspaceTrustBanner workspacePath={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when the folder holds nothing that needs a decision', async () => {
    const preview = vi
      .spyOn(workspaceTrustService, 'previewWorkspaceTrustManifest')
      .mockResolvedValue(manifest({ current_level: 'TRUSTED', requires_trust: false }));

    const { container } = render(<WorkspaceTrustBanner workspacePath="/tmp/repo" />);
    await waitFor(() => expect(preview).toHaveBeenCalled());
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing for a trusted folder whose shortcuts the user has already seen', async () => {
    const preview = vi
      .spyOn(workspaceTrustService, 'previewWorkspaceTrustManifest')
      .mockResolvedValue(
        manifest({ current_level: 'TRUSTED', repo_command_prefixes: ['npm run test'], pending_command_prefixes: [] }),
      );

    const { container } = render(<WorkspaceTrustBanner workspacePath="/tmp/repo" />);
    await waitFor(() => expect(preview).toHaveBeenCalled());
    expect(container.firstChild).toBeNull();
  });

  describe('restricted folder', () => {
    it('says what is turned off, with counts', async () => {
      vi.spyOn(workspaceTrustService, 'previewWorkspaceTrustManifest').mockResolvedValue(
        manifest({ skill_count: 2, rule_count: 1, mcp_count: 1 }),
      );

      render(<WorkspaceTrustBanner workspacePath="/tmp/repo" />);

      await waitFor(() => expect(screen.getByText('restrictedTitle')).toBeTruthy());
      expect(screen.getByText('restrictedMessage:{"path":"/tmp/repo"}')).toBeTruthy();
      expect(screen.getByRole('button', { name: 'trustAction' })).toBeTruthy();

      fireEvent.click(screen.getByRole('button', { name: /detailsToggle/ }));
      expect(screen.getByText('itemSkills:{"count":2}')).toBeTruthy();
      expect(screen.getByText('itemMcp:{"count":1}')).toBeTruthy();
      expect(screen.getByText('itemRules:{"count":1}')).toBeTruthy();
    });

    it('lists the command shortcuts that trusting would also allow', async () => {
      vi.spyOn(workspaceTrustService, 'previewWorkspaceTrustManifest').mockResolvedValue(
        manifest({
          skill_count: 1,
          repo_command_prefixes: ['npm run test'],
          pending_command_prefixes: ['npm run test'],
        }),
      );

      render(<WorkspaceTrustBanner workspacePath="/tmp/repo" />);
      await waitFor(() => expect(screen.getByText('restrictedTitle')).toBeTruthy());
      expect(screen.queryByText('npm run test')).toBeNull();

      fireEvent.click(screen.getByRole('button', { name: /detailsToggle/ }));
      expect(screen.getByLabelText('shortcutsOnTrust').textContent).toContain('npm run test');
    });

    it('trusts the previewed folder state and notifies the caller', async () => {
      const onTrustChanged = vi.fn();
      vi.spyOn(workspaceTrustService, 'previewWorkspaceTrustManifest').mockResolvedValue(
        manifest({ skill_count: 1, manifest_hash: 'hash-restricted' }),
      );
      const decide = vi.spyOn(workspaceTrustService, 'decideWorkspaceTrust').mockResolvedValue(entry);

      render(<WorkspaceTrustBanner workspacePath="/tmp/repo" onTrustChanged={onTrustChanged} />);
      await waitFor(() => expect(screen.getByText('restrictedTitle')).toBeTruthy());

      fireEvent.click(screen.getByRole('button', { name: 'trustAction' }));

      await waitFor(() => {
        expect(decide).toHaveBeenCalledWith('/tmp/repo', 'TRUSTED', 'hash-restricted');
        expect(onTrustChanged).toHaveBeenCalledWith('TRUSTED');
      });
      expect(toast).toHaveBeenCalledWith({ title: 'trusted' });
    });
  });

  describe('trusted folder with command shortcuts the user has not seen', () => {
    const pending = () =>
      manifest({
        current_level: 'TRUSTED',
        skill_count: 1,
        repo_command_prefixes: ['npm run test', 'curl'],
        pending_command_prefixes: ['curl'],
        manifest_hash: 'hash-pending',
      });

    it('shows the shortcuts waiting for approval without any click', async () => {
      vi.spyOn(workspaceTrustService, 'previewWorkspaceTrustManifest').mockResolvedValue(pending());

      render(<WorkspaceTrustBanner workspacePath="/tmp/repo" />);

      await waitFor(() => expect(screen.getByText('pendingTitle')).toBeTruthy());
      expect(screen.getByLabelText('pendingList').textContent).toBe('curl');
      expect(screen.queryByText('restrictedTitle')).toBeNull();
    });

    it('allows them against the previewed folder state', async () => {
      const onTrustChanged = vi.fn();
      vi.spyOn(workspaceTrustService, 'previewWorkspaceTrustManifest').mockResolvedValue(pending());
      const decide = vi.spyOn(workspaceTrustService, 'decideWorkspaceTrust').mockResolvedValue(entry);

      render(<WorkspaceTrustBanner workspacePath="/tmp/repo" onTrustChanged={onTrustChanged} />);
      await waitFor(() => expect(screen.getByText('pendingTitle')).toBeTruthy());

      fireEvent.click(screen.getByRole('button', { name: 'allowAction' }));

      await waitFor(() => expect(decide).toHaveBeenCalledWith('/tmp/repo', 'TRUSTED', 'hash-pending'));
      expect(onTrustChanged).toHaveBeenCalledWith('TRUSTED');
      expect(toast).toHaveBeenCalledWith({ title: 'shortcutsAllowed' });
    });

    it('reports a refused decision and shows the folder as it is now', async () => {
      const preview = vi
        .spyOn(workspaceTrustService, 'previewWorkspaceTrustManifest')
        .mockResolvedValueOnce(pending())
        .mockResolvedValue(
          manifest({
            current_level: 'TRUSTED',
            repo_command_prefixes: ['npm run test', 'curl', 'rm'],
            pending_command_prefixes: ['curl', 'rm'],
            manifest_hash: 'hash-changed',
          }),
        );
      const decide = vi
        .spyOn(workspaceTrustService, 'decideWorkspaceTrust')
        .mockRejectedValueOnce(new Error('Folder preview is missing or out of date.'));
      const onTrustChanged = vi.fn();

      render(<WorkspaceTrustBanner workspacePath="/tmp/repo" onTrustChanged={onTrustChanged} />);
      await waitFor(() => expect(screen.getByText('pendingTitle')).toBeTruthy());

      fireEvent.click(screen.getByRole('button', { name: 'allowAction' }));

      await waitFor(() => expect(screen.getByLabelText('pendingList').textContent).toContain('rm'));
      expect(toast).toHaveBeenCalledWith({ title: 'trustFailed', variant: 'destructive' });
      expect(onTrustChanged).not.toHaveBeenCalled();
      expect(preview).toHaveBeenCalledTimes(2);

      decide.mockResolvedValueOnce(entry);
      fireEvent.click(screen.getByRole('button', { name: 'allowAction' }));
      await waitFor(() => expect(decide).toHaveBeenLastCalledWith('/tmp/repo', 'TRUSTED', 'hash-changed'));
    });
  });
});
