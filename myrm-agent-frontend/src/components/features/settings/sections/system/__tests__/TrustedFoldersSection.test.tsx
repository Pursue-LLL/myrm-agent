import { render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import TrustedFoldersSection from '../TrustedFoldersSection';
import * as workspaceTrustService from '@/services/workspaceTrust';

// Echo the interpolation values too, so counts are asserted along with the keys.
const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key}:${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock('@/lib/directoryBrowseRecent', () => ({
  shortenHomePath: (path: string) => path,
}));

function entry(overrides: Partial<workspaceTrustService.WorkspaceTrustEntry> = {}) {
  return {
    path: '/tmp/repo',
    level: 'TRUSTED' as const,
    decided_at: '2026-09-27T00:00:00Z',
    manifest_hash: 'hash-1',
    disclosed_command_prefixes: [],
    ...overrides,
  };
}

describe('TrustedFoldersSection', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('lists the commands a trusted folder was approved to run without asking', async () => {
    vi.spyOn(workspaceTrustService, 'listTrustedFolders').mockResolvedValue([
      entry({ disclosed_command_prefixes: ['npm run test', 'make lint'] }),
    ]);

    render(<TrustedFoldersSection />);

    const commands = await screen.findByLabelText('commands');
    expect(within(commands).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'npm run test',
      'make lint',
    ]);
  });

  it('lists the commands of each folder under that folder only', async () => {
    vi.spyOn(workspaceTrustService, 'listTrustedFolders').mockResolvedValue([
      entry({ path: '/tmp/a', disclosed_command_prefixes: ['npm run test'] }),
      entry({ path: '/tmp/b' }),
    ]);

    render(<TrustedFoldersSection />);

    await waitFor(() => expect(screen.getByText('/tmp/b')).toBeTruthy());
    expect(screen.getAllByLabelText('commands')).toHaveLength(1);
  });

  it('shows no command list for a folder with nothing approved', async () => {
    vi.spyOn(workspaceTrustService, 'listTrustedFolders').mockResolvedValue([entry({ level: 'RESTRICTED' })]);

    render(<TrustedFoldersSection />);

    await waitFor(() => expect(screen.getByText('/tmp/repo')).toBeTruthy());
    expect(screen.queryByLabelText('commands')).toBeNull();
  });
});
