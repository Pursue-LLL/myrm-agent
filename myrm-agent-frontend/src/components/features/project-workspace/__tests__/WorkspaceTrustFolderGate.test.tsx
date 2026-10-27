import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import WorkspaceTrustFolderGate from '../WorkspaceTrustFolderGate';
import * as workspaceTrustService from '@/services/workspaceTrust';

vi.mock('@/lib/directoryBrowseRecent', () => ({
  shortenHomePath: (p: string) => p,
}));

function manifest(overrides: Partial<workspaceTrustService.WorkspaceTrustManifest> = {}) {
  return {
    path: '/tmp/repo',
    canonical_path: '/tmp/repo',
    skill_count: 1,
    rule_count: 0,
    mcp_count: 2,
    plugin_count: 0,
    repo_command_prefixes: ['npm run test'],
    pending_command_prefixes: ['npm run test'],
    has_myrm_config: true,
    current_level: null,
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

function renderGate(onDecided = vi.fn()) {
  render(<WorkspaceTrustFolderGate open folderPath="/tmp/repo" onOpenChange={vi.fn()} onDecided={onDecided} />);
  return onDecided;
}

describe('WorkspaceTrustFolderGate', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('discloses local MCP servers through translated copy', async () => {
    vi.spyOn(workspaceTrustService, 'previewWorkspaceTrustManifest').mockResolvedValue(manifest());

    renderGate();

    await waitFor(() => expect(screen.getByText('mcpServers')).toBeTruthy());
    expect(screen.getByText('npm run test')).toBeTruthy();
  });

  it.each([
    ['trust', 'TRUSTED'],
    ['restrict', 'RESTRICTED'],
  ] as const)('sends the previewed hash when the user picks %s', async (label, level) => {
    vi.spyOn(workspaceTrustService, 'previewWorkspaceTrustManifest').mockResolvedValue(
      manifest({ manifest_hash: 'hash-previewed' }),
    );
    const decide = vi.spyOn(workspaceTrustService, 'decideWorkspaceTrust').mockResolvedValue(entry);
    const onDecided = renderGate();
    await waitFor(() => expect(screen.getByText('mcpServers')).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: new RegExp(`^${label}$`) }));

    await waitFor(() => expect(onDecided).toHaveBeenCalledWith('/tmp/repo', level));
    expect(decide).toHaveBeenCalledWith('/tmp/repo', level, 'hash-previewed');
  });

  it('re-scans after a refused decision so the retry carries the current hash', async () => {
    const preview = vi
      .spyOn(workspaceTrustService, 'previewWorkspaceTrustManifest')
      .mockResolvedValueOnce(manifest({ manifest_hash: 'hash-old' }))
      .mockResolvedValue(manifest({ manifest_hash: 'hash-new', repo_command_prefixes: ['npm run test', 'curl'] }));
    const decide = vi
      .spyOn(workspaceTrustService, 'decideWorkspaceTrust')
      .mockRejectedValueOnce(new Error('Folder preview is missing or out of date.'))
      .mockResolvedValue(entry);
    const onDecided = renderGate();
    await waitFor(() => expect(screen.getByText('mcpServers')).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: /^trust$/ }));

    await waitFor(() => expect(screen.getByText('decideFailed')).toBeTruthy());
    expect(onDecided).not.toHaveBeenCalled();
    expect(preview).toHaveBeenCalledTimes(2);
    expect(screen.getByText('curl')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /^trust$/ }));
    await waitFor(() => expect(decide).toHaveBeenLastCalledWith('/tmp/repo', 'TRUSTED', 'hash-new'));
  });
});
