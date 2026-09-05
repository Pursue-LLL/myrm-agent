/** @vitest-environment jsdom */
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { RepoEvidenceCard } from '../cards/RepoEvidenceCard';
import * as commandCenterService from '@/services/memory/commandCenter';

const stableT = (key: string, values?: Record<string, unknown>) => {
  if (values) {
    return Object.entries(values).reduce(
      (acc, [k, v]) => acc.replace(`{${k}}`, String(v)),
      key
    );
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('RepoEvidenceCard Component', () => {
  const mockRepoDigest: commandCenterService.MemoryRepoEvidenceResponse = {
    repo_name: 'open-perplexity',
    repo_path: '/path/to/open-perplexity',
    current_branch: 'main',
    is_dirty: true,
    recent_commits: [
      {
        commit_hash: '1234567890abcdef1234567890abcdef12345678',
        short_hash: '12345678',
        author: 'Bob Developer',
        committed_at: '2026-09-05T03:00:00Z',
        subject: 'feat: support repo history evidence',
        files_changed: ['src/git.ts', 'src/card.tsx'],
      },
    ],
    total_commits_examined: 1,
    extracted_at: '2026-09-05T03:00:00Z',
    is_git_available: true,
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders repository name, branch, and uncommitted changes badge', async () => {
    vi.spyOn(commandCenterService, 'getRepoEvidenceDigest').mockResolvedValueOnce(mockRepoDigest);

    render(<RepoEvidenceCard workspacePath="/path/to/open-perplexity" />);

    await waitFor(() => {
      expect(screen.getByText('open-perplexity')).toBeDefined();
      expect(screen.getByText('main')).toBeDefined();
      expect(screen.getByText('uncommittedChanges')).toBeDefined();
      expect(screen.getByText('feat: support repo history evidence')).toBeDefined();
      expect(screen.getByText('12345678')).toBeDefined();
      expect(screen.getByText('Bob Developer')).toBeDefined();
    });
  });

  it('renders error state on API rejection', async () => {
    vi.spyOn(commandCenterService, 'getRepoEvidenceDigest').mockRejectedValueOnce(
      new Error('Git command failed')
    );

    render(<RepoEvidenceCard workspacePath="/invalid/path" />);

    await waitFor(() => {
      expect(screen.getByText('Git command failed')).toBeDefined();
    });
  });
});
