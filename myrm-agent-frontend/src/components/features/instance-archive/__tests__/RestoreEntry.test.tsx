/** @vitest-environment jsdom */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ArchiveStatus } from '@/services/instanceArchive';
import { RestoreEntry } from '../RestoreEntry';

const { service } = vi.hoisted(() => ({ service: { getStatus: vi.fn() } }));

vi.mock('@/services/instanceArchive', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/instanceArchive')>()),
  instanceArchiveService: service,
}));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('../ImportCard', () => ({
  ImportCard: ({ onQueued }: { onQueued: () => void }) => (
    <button type="button" data-testid="import-card" onClick={onQueued}>
      wizard
    </button>
  ),
}));

const status = (overrides: Partial<ArchiveStatus> = {}): ArchiveStatus => ({
  supported: true,
  can_protect_secrets: true,
  restart_mode: 'process',
  pending_operation: null,
  rollback_available: false,
  ...overrides,
});

const settled = () =>
  act(async () => {
    await Promise.resolve();
  });

beforeEach(() => {
  vi.clearAllMocks();
});

describe('RestoreEntry', () => {
  it('renders nothing where backups are unsupported, so the prompt never leads nowhere', async () => {
    service.getStatus.mockResolvedValue(status({ supported: false }));

    const { container } = render(<RestoreEntry />);
    await waitFor(() => expect(service.getStatus).toHaveBeenCalledTimes(1));
    await settled();

    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when the workspace cannot report its capabilities', async () => {
    service.getStatus.mockRejectedValue(new Error('unreachable'));

    const { container } = render(<RestoreEntry />);
    await waitFor(() => expect(service.getStatus).toHaveBeenCalledTimes(1));
    await settled();

    expect(container).toBeEmptyDOMElement();
  });

  it('offers the restore collapsed and keeps the wizard mounted across a toggle', async () => {
    service.getStatus.mockResolvedValue(status());

    render(<RestoreEntry />);
    const toggle = await screen.findByRole('button', { name: 'open' });

    expect(screen.getByText('prompt')).toBeInTheDocument();
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByTestId('import-card')).not.toBeVisible();

    fireEvent.click(toggle);

    expect(screen.getByRole('button', { name: 'close' })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByTestId('import-card')).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: 'close' }));

    expect(screen.getByTestId('import-card')).not.toBeVisible();
    expect(screen.getByRole('button', { name: 'open' })).toBeInTheDocument();
  });

  it('asks for a restart once the wizard has queued a restore, even while collapsed', async () => {
    service.getStatus.mockResolvedValueOnce(status()).mockResolvedValueOnce(status({ pending_operation: 'import' }));

    render(<RestoreEntry />);
    await screen.findByRole('button', { name: 'open' });
    expect(screen.queryByText('title')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('import-card'));

    expect(await screen.findByText('title')).toBeInTheDocument();
    expect(service.getStatus).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId('import-card')).not.toBeVisible();
  });
});
