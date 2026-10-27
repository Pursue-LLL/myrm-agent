/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

import { RemoteFileList } from '../RemoteFileList';
import type { RemoteBackupFile } from '../remoteBackupApi';
import type { ListState } from '../useRemoteBackup';

const FILE: RemoteBackupFile = {
  file_name: 'myrm.20261026120000.macbook-pro.a1b2c3d4.darwin.json.gz',
  modified_time: '2026-10-26T12:00:00Z',
  size_bytes: 12600,
};

function setup(state: ListState, files: RemoteBackupFile[] = []) {
  const handlers = { onRefresh: vi.fn(), onRestore: vi.fn(), onDelete: vi.fn() };
  render(<RemoteFileList files={files} state={state} {...handlers} />);
  return handlers;
}

describe('what the list says about the storage', () => {
  it('asks for a connection test before anything has been read', () => {
    setup('idle');

    expect(screen.getByText('listIdle')).toBeInTheDocument();
  });

  it('says it is reading while the first answer is outstanding', () => {
    setup('loading');

    expect(screen.getByText('loadingFiles')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'refreshList' })).toBeDisabled();
  });

  it('says there are no backups only for a storage it could read', () => {
    setup('ready');

    expect(screen.getByText('noRemoteFiles')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('says a storage it could not read could not be read, and offers a retry, never "no backups"', async () => {
    const { onRefresh } = setup('error');

    expect(screen.getByRole('alert')).toHaveTextContent('listError');
    expect(screen.queryByText('noRemoteFiles')).not.toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole('button', { name: 'retry' }));
    expect(onRefresh).toHaveBeenCalledOnce();
  });

  it('keeps showing the backups already listed while it reads again', () => {
    setup('loading', [FILE]);

    expect(screen.queryByText('loadingFiles')).not.toBeInTheDocument();
    expect(screen.getByText('12.3 KB · macbook-pro')).toBeInTheDocument();
  });
});

describe('a backup row', () => {
  it('shows when, how big and from which device, and keeps the raw file name out of sight', () => {
    setup('ready', [FILE]);

    expect(screen.getByText('12.3 KB · macbook-pro')).toBeInTheDocument();
    expect(screen.queryByText(FILE.file_name)).not.toBeInTheDocument();
    expect(screen.getByRole('listitem')).toHaveAttribute('title', FILE.file_name);
  });

  it('falls back to the file name when the time cannot be read', () => {
    setup('ready', [{ ...FILE, modified_time: 'not a time' }]);

    expect(screen.getByText(FILE.file_name)).toBeInTheDocument();
  });

  it('omits the device of a name that does not carry one', () => {
    setup('ready', [{ ...FILE, file_name: 'myrm.20260101000000.old-host.linux.json.gz' }]);

    expect(screen.getByText('12.3 KB')).toBeInTheDocument();
  });
});

describe('restoring and deleting', () => {
  it('restores only after the dialog says it merges and removes nothing', async () => {
    const user = userEvent.setup();
    const { onRestore } = setup('ready', [FILE]);

    await user.click(screen.getByRole('button', { name: 'restoreFromCloud' }));
    const dialog = screen.getByRole('alertdialog');
    expect(within(dialog).getByText('restoreDescription')).toBeInTheDocument();
    expect(within(dialog).getByText(FILE.file_name)).toBeInTheDocument();
    expect(onRestore).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole('button', { name: 'restoreFromCloud' }));
    expect(onRestore).toHaveBeenCalledExactlyOnceWith(FILE.file_name);
  });

  it('deletes only after the dialog says it cannot be undone', async () => {
    const user = userEvent.setup();
    const { onDelete } = setup('ready', [FILE]);

    await user.click(screen.getByRole('button', { name: 'deleteFromCloud' }));
    const dialog = screen.getByRole('alertdialog');
    expect(within(dialog).getByText('deleteDescription')).toBeInTheDocument();

    await user.click(within(dialog).getByRole('button', { name: 'deleteFromCloud' }));
    expect(onDelete).toHaveBeenCalledExactlyOnceWith(FILE.file_name);
  });

  it('does nothing when the dialog is cancelled', async () => {
    const user = userEvent.setup();
    const { onRestore, onDelete } = setup('ready', [FILE]);

    await user.click(screen.getByRole('button', { name: 'deleteFromCloud' }));
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'cancel' }));

    expect(onDelete).not.toHaveBeenCalled();
    expect(onRestore).not.toHaveBeenCalled();
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });
});
