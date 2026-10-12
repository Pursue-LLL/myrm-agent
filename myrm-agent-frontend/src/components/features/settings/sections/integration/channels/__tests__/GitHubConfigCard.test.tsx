/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const mocks = vi.hoisted(() => ({
  getGitHubCredentials: vi.fn(),
  testGitHubConnection: vi.fn(),
}));

vi.mock('@/services/channels', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    getGitHubCredentials: (...args: unknown[]) => mocks.getGitHubCredentials(...args),
    testGitHubConnection: (...args: unknown[]) => mocks.testGitHubConnection(...args),
  };
});

import { GitHubConfigCard } from '../GitHubConfigCard';

describe('GitHubConfigCard', () => {
  beforeEach(() => {
    mocks.getGitHubCredentials.mockResolvedValue({ personalAccessToken: 'ghp_saved' });
    mocks.testGitHubConnection.mockResolvedValue({ ok: true });
  });

  it('asks for the access token and nothing else', async () => {
    const { container } = render(<GitHubConfigCard />);

    expect(await screen.findByLabelText('githubPersonalAccessToken')).toHaveValue('ghp_saved');
    expect(container.querySelectorAll('input')).toHaveLength(1);
    expect(screen.queryByText(/webhook/i)).not.toBeInTheDocument();
  });
});
