/** @vitest-environment jsdom */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { AutoBackup } from '@/services/instanceAutoBackup';
import { AutoBackupCard } from '../AutoBackupCard';
import { apiError, DEFAULT_DIR, snapshot } from './autoBackupTestKit';

const { service, bridge } = vi.hoisted(() => ({
  service: { get: vi.fn(), update: vi.fn(), runNow: vi.fn() },
  bridge: { isDesktop: vi.fn(), openDirectoryPicker: vi.fn() },
}));

vi.mock('@/services/instanceAutoBackup', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/instanceAutoBackup')>()),
  instanceAutoBackupService: service,
}));
vi.mock('@/lib/desktopBridge', () => ({ desktopBridge: bridge }));

const stableT = (key: string, params?: Record<string, unknown>) =>
  params ? `${key}:${Object.values(params).join('|')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

const UNREADABLE_DIR = '/Volumes/Backup-Disk/Backups';

/** Turned off, pointing at a folder the user chose that cannot be read now (unplugged drive): nothing is listed from it. */
const unreadableCustomFolder = (): AutoBackup =>
  snapshot({
    enabled: false,
    default_directory: false,
    directory: UNREADABLE_DIR,
    folder_available: false,
    backups: [],
    last_success_at: null,
    last_success_size: null,
  });

/** jsdom lacks the pointer and scroll APIs Radix Select calls while opening its list. */
const shimPointerApisUsedBySelect = () => {
  for (const name of ['hasPointerCapture', 'releasePointerCapture', 'scrollIntoView'] as const) {
    Object.defineProperty(Element.prototype, name, { value: () => false, configurable: true });
  }
};

beforeEach(() => {
  vi.clearAllMocks();
  bridge.isDesktop.mockReturnValue(false);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('AutoBackupCard visibility', () => {
  it('renders nothing where scheduled backups are not offered', async () => {
    service.get.mockResolvedValue(snapshot({ supported: false, enabled: false, backups: [] }));

    const { container } = render(<AutoBackupCard />);
    await waitFor(() => expect(service.get).toHaveBeenCalled());

    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when the endpoint cannot be read', async () => {
    service.get.mockRejectedValue(apiError('forbidden', 403));

    const { container } = render(<AutoBackupCard />);
    await waitFor(() => expect(service.get).toHaveBeenCalled());

    expect(container).toBeEmptyDOMElement();
  });
});

describe('AutoBackupCard when turned off', () => {
  it('shows only the switch and the limits, nothing to configure', async () => {
    service.get.mockResolvedValue(snapshot({ enabled: false, backups: [], last_success_at: null }));

    render(<AutoBackupCard />);

    expect(await screen.findByRole('switch', { name: 'enable' })).not.toBeChecked();
    expect(screen.getByText('notePlain')).toBeInTheDocument();
    expect(screen.getByText('noteScope')).toBeInTheDocument();
    expect(screen.queryByLabelText('folder')).not.toBeInTheDocument();
    expect(screen.queryByText('frequency')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'backupNow' })).not.toBeInTheDocument();
  });

  it('turns on with the shown defaults and the default folder', async () => {
    service.get.mockResolvedValue(snapshot({ enabled: false, backups: [], last_success_at: null }));
    service.update.mockResolvedValue(snapshot({ running: true }));

    render(<AutoBackupCard />);
    fireEvent.click(await screen.findByRole('switch', { name: 'enable' }));

    await waitFor(() =>
      expect(service.update).toHaveBeenCalledWith({
        enabled: true,
        frequency: 'daily',
        keep: 3,
        directory: null,
      }),
    );
    expect(await screen.findByRole('button', { name: 'running' })).toBeDisabled();
  });

  it('turns off without touching the saved folder choice', async () => {
    service.get.mockResolvedValue(snapshot({ default_directory: false, directory: '/Volumes/Safe' }));
    service.update.mockResolvedValue(
      snapshot({ enabled: false, default_directory: false, directory: '/Volumes/Safe' }),
    );

    render(<AutoBackupCard />);
    fireEvent.click(await screen.findByRole('switch', { name: 'enable' }));

    await waitFor(() =>
      expect(service.update).toHaveBeenCalledWith({
        enabled: false,
        frequency: 'daily',
        keep: 3,
        directory: '/Volumes/Safe',
      }),
    );
    await waitFor(() => expect(screen.queryByText('frequency')).not.toBeInTheDocument());
  });
});

describe('AutoBackupCard after being turned off', () => {
  it('keeps the copies already made and their folder in view, without the schedule controls', async () => {
    service.get.mockResolvedValue(snapshot({ enabled: false }));

    render(<AutoBackupCard />);

    expect(await screen.findByText('savedCopies:2')).toBeInTheDocument();
    expect(screen.getByText('restoreHint')).toBeInTheDocument();
    expect(screen.getByLabelText('folder')).toHaveValue(DEFAULT_DIR);
    expect(screen.queryByText('frequency')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'backupNow' })).not.toBeInTheDocument();
  });

  it('keeps a folder the user chose in view even when no copy can be listed from it', async () => {
    service.get.mockResolvedValue(unreadableCustomFolder());

    render(<AutoBackupCard />);

    expect(await screen.findByLabelText('folder')).toHaveValue(UNREADABLE_DIR);
    expect(screen.getByRole('button', { name: 'useDefault' })).toBeInTheDocument();
    expect(screen.queryByText('frequency')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'backupNow' })).not.toBeInTheDocument();
    expect(screen.queryByText(/^savedCopies/)).not.toBeInTheDocument();
  });

  it('leaves a way out when turning it on is refused because the chosen folder cannot be used', async () => {
    service.get.mockResolvedValue(unreadableCustomFolder());
    service.update
      .mockRejectedValueOnce(apiError('backup_dir_invalid'))
      .mockResolvedValue(snapshot({ enabled: false, backups: [], last_success_at: null }));

    render(<AutoBackupCard />);
    fireEvent.click(await screen.findByRole('switch', { name: 'enable' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('backup_dir_invalid');
    expect(screen.getByRole('switch', { name: 'enable' })).not.toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: 'useDefault' }));

    await waitFor(() =>
      expect(service.update).toHaveBeenLastCalledWith({ enabled: false, frequency: 'daily', keep: 3, directory: null }),
    );
    await waitFor(() => expect(screen.queryByLabelText('folder')).not.toBeInTheDocument());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('saves another folder while turned off, without turning it on', async () => {
    service.get.mockResolvedValue(unreadableCustomFolder());
    service.update.mockResolvedValue(
      snapshot({ enabled: false, default_directory: false, directory: '/Volumes/New-Disk/Backups', backups: [] }),
    );

    render(<AutoBackupCard />);
    fireEvent.change(await screen.findByLabelText('folder'), { target: { value: '/Volumes/New-Disk/Backups' } });
    fireEvent.click(screen.getByRole('button', { name: 'apply' }));

    await waitFor(() =>
      expect(service.update).toHaveBeenCalledWith({
        enabled: false,
        frequency: 'daily',
        keep: 3,
        directory: '/Volumes/New-Disk/Backups',
      }),
    );
    expect(await screen.findByLabelText('folder')).toHaveValue('/Volumes/New-Disk/Backups');
    expect(screen.getByRole('switch', { name: 'enable' })).not.toBeChecked();
  });
});

describe('AutoBackupCard when turned on', () => {
  it('shows the last backup and the saved copies, and how to restore one', async () => {
    service.get.mockResolvedValue(snapshot());

    render(<AutoBackupCard />);

    expect(await screen.findByText(/^lastBackup:/)).toHaveTextContent('4.1 MB');
    expect(screen.getByText('savedCopies:2')).toBeInTheDocument();
    expect(screen.getByText('restoreHint')).toBeInTheDocument();
    expect(screen.getByText('defaultFolderHint')).toBeInTheDocument();
    expect(screen.queryByText('myrm-auto-backup-3fa9c2d1-20261012-083000.zip')).not.toBeInTheDocument();
  });

  it('says so when no backup has completed yet', async () => {
    service.get.mockResolvedValue(snapshot({ last_success_at: null, last_success_size: null, backups: [] }));

    render(<AutoBackupCard />);

    expect(await screen.findByText('noBackupYet')).toBeInTheDocument();
    expect(screen.queryByText(/^savedCopies/)).not.toBeInTheDocument();
  });

  it('warns when the last backup is much older than the schedule', async () => {
    service.get.mockResolvedValue(snapshot({ overdue: true }));

    render(<AutoBackupCard />);

    expect(await screen.findByText('overdue')).toBeInTheDocument();
  });

  it('changes the frequency and keeps every other setting', async () => {
    service.get.mockResolvedValue(snapshot({ keep: 5, default_directory: false, directory: '/Volumes/Safe' }));
    service.update.mockResolvedValue(snapshot({ frequency: 'weekly' }));

    render(<AutoBackupCard />);
    fireEvent.click(await screen.findByRole('radio', { name: 'frequencyOptions.weekly' }));

    await waitFor(() =>
      expect(service.update).toHaveBeenCalledWith({
        enabled: true,
        frequency: 'weekly',
        keep: 5,
        directory: '/Volumes/Safe',
      }),
    );
  });

  it('offers a stored keep count that is not among the usual choices', async () => {
    service.get.mockResolvedValue(snapshot({ keep: 4 }));

    render(<AutoBackupCard />);

    expect(await screen.findByRole('combobox', { name: 'keep' })).toHaveTextContent('keepOption:4');
  });

  it('changes how many copies to keep and leaves every other setting alone', async () => {
    shimPointerApisUsedBySelect();
    service.get.mockResolvedValue(snapshot({ frequency: 'weekly' }));
    service.update.mockResolvedValue(snapshot({ frequency: 'weekly', keep: 7 }));

    render(<AutoBackupCard />);
    fireEvent.keyDown(await screen.findByRole('combobox', { name: 'keep' }), { key: 'ArrowDown' });
    fireEvent.click(await screen.findByRole('option', { name: 'keepOption:7' }));

    await waitFor(() =>
      expect(service.update).toHaveBeenCalledWith({ enabled: true, frequency: 'weekly', keep: 7, directory: null }),
    );
  });

  it('starts a backup on request and follows it until it finishes', async () => {
    vi.useFakeTimers();
    service.get
      .mockResolvedValueOnce(snapshot())
      .mockResolvedValue(snapshot({ last_success_at: '2026-10-13T09:00:00Z' }));
    service.runNow.mockResolvedValue(snapshot({ running: true }));

    render(<AutoBackupCard />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    fireEvent.click(screen.getByRole('button', { name: 'backupNow' }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(service.runNow).toHaveBeenCalledOnce();
    expect(screen.getByRole('button', { name: 'running' })).toBeDisabled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(screen.getByRole('button', { name: 'backupNow' })).toBeEnabled();
    expect(service.get).toHaveBeenCalledTimes(2);
  });

  it('keeps polling quiet after the run is over', async () => {
    vi.useFakeTimers();
    service.get.mockResolvedValue(snapshot());

    render(<AutoBackupCard />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(service.get).toHaveBeenCalledTimes(1);
  });
});

describe('AutoBackupCard errors', () => {
  it('explains a refused folder in plain words, never with server wording', async () => {
    service.get.mockResolvedValue(snapshot({ default_directory: false, directory: '/Volumes/Safe' }));
    service.update.mockRejectedValue(apiError('backup_dir_not_writable'));

    render(<AutoBackupCard />);
    fireEvent.change(await screen.findByLabelText('folder'), { target: { value: '/readonly' } });
    fireEvent.click(screen.getByRole('button', { name: 'apply' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('backup_dir_not_writable');
    expect(screen.queryByText('server wording')).not.toBeInTheDocument();
  });

  it('falls back to the generic message for a code it has no copy for', async () => {
    service.get.mockResolvedValue(snapshot());
    service.runNow.mockRejectedValue(apiError('some_internal_failure', 500));

    render(<AutoBackupCard />);
    fireEvent.click(await screen.findByRole('button', { name: 'backupNow' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('generic');
  });

  it('shows the busy export reason when a manual backup is in progress', async () => {
    service.get.mockResolvedValue(snapshot());
    service.runNow.mockRejectedValue(apiError('export_busy', 409));

    render(<AutoBackupCard />);
    fireEvent.click(await screen.findByRole('button', { name: 'backupNow' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('export_busy');
  });

  it('clears the error once the next action succeeds', async () => {
    service.get.mockResolvedValue(snapshot());
    service.runNow.mockRejectedValueOnce(apiError('export_busy', 409)).mockResolvedValue(snapshot({ running: true }));

    render(<AutoBackupCard />);
    fireEvent.click(await screen.findByRole('button', { name: 'backupNow' }));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: 'backupNow' }));

    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  });
});
