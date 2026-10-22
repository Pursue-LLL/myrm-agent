/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AutoBackupCard } from '../AutoBackupCard';
import { DEFAULT_DIR, snapshot } from './autoBackupTestKit';

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

beforeEach(() => {
  vi.clearAllMocks();
  bridge.isDesktop.mockReturnValue(false);
});

describe('AutoBackupLocation', () => {
  it('applies a typed folder only once it differs and is not blank', async () => {
    service.get.mockResolvedValue(snapshot());
    service.update.mockResolvedValue(snapshot({ default_directory: false, directory: '/Volumes/Safe' }));

    render(<AutoBackupCard />);
    const input = await screen.findByLabelText('folder');
    expect(screen.queryByRole('button', { name: 'apply' })).not.toBeInTheDocument();

    fireEvent.change(input, { target: { value: '   ' } });
    expect(screen.getByRole('button', { name: 'apply' })).toBeDisabled();

    fireEvent.change(input, { target: { value: '  /Volumes/Safe  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'apply' }));

    await waitFor(() =>
      expect(service.update).toHaveBeenCalledWith({
        enabled: true,
        frequency: 'daily',
        keep: 3,
        directory: '/Volumes/Safe',
      }),
    );
  });

  it('returns to the default folder', async () => {
    service.get.mockResolvedValue(snapshot({ default_directory: false, directory: '/Volumes/Safe' }));
    service.update.mockResolvedValue(snapshot());

    render(<AutoBackupCard />);
    expect(await screen.findByText('folderHint')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'useDefault' }));

    await waitFor(() =>
      expect(service.update).toHaveBeenCalledWith({ enabled: true, frequency: 'daily', keep: 3, directory: null }),
    );
    expect(await screen.findByText('defaultFolderHint')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'useDefault' })).not.toBeInTheDocument();
  });

  it('has no folder picker in a browser', async () => {
    service.get.mockResolvedValue(snapshot());

    render(<AutoBackupCard />);
    await screen.findByLabelText('folder');

    expect(screen.queryByRole('button', { name: 'browse' })).not.toBeInTheDocument();
  });

  it('saves the folder picked in the desktop app straight away', async () => {
    bridge.isDesktop.mockReturnValue(true);
    bridge.openDirectoryPicker.mockResolvedValue('/Volumes/Backup');
    service.get.mockResolvedValue(snapshot());
    service.update.mockResolvedValue(snapshot({ default_directory: false, directory: '/Volumes/Backup' }));

    render(<AutoBackupCard />);
    fireEvent.click(await screen.findByRole('button', { name: 'browse' }));

    await waitFor(() =>
      expect(service.update).toHaveBeenCalledWith({
        enabled: true,
        frequency: 'daily',
        keep: 3,
        directory: '/Volumes/Backup',
      }),
    );
    expect(bridge.openDirectoryPicker).toHaveBeenCalledWith({ title: 'browseTitle', defaultPath: DEFAULT_DIR });
    expect(await screen.findByLabelText('folder')).toHaveValue('/Volumes/Backup');
  });

  it('keeps the current folder when the picker is dismissed', async () => {
    bridge.isDesktop.mockReturnValue(true);
    bridge.openDirectoryPicker.mockResolvedValue(null);
    service.get.mockResolvedValue(snapshot());

    render(<AutoBackupCard />);
    fireEvent.click(await screen.findByRole('button', { name: 'browse' }));
    await waitFor(() => expect(bridge.openDirectoryPicker).toHaveBeenCalled());

    expect(service.update).not.toHaveBeenCalled();
    expect(screen.getByLabelText('folder')).toHaveValue(DEFAULT_DIR);
  });
});
