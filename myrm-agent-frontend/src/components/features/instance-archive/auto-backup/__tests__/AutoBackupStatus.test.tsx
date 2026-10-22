/** @vitest-environment jsdom */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { AutoBackup } from '@/services/instanceAutoBackup';
import { AutoBackupStatus } from '../AutoBackupStatus';

const stableT = (key: string, params?: Record<string, unknown>) =>
  params ? `${key}:${Object.values(params).join('|')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

const neverBackedUp = (overrides: Partial<AutoBackup> = {}): AutoBackup => ({
  supported: true,
  enabled: true,
  frequency: 'daily',
  keep: 3,
  directory: '/Volumes/Safe',
  default_directory: false,
  folder_available: true,
  running: false,
  overdue: false,
  last_success_at: null,
  last_success_size: null,
  consecutive_failures: 0,
  last_error_code: null,
  backups: [],
  ...overrides,
});

describe('AutoBackupStatus when the folder cannot be read', () => {
  it('says the folder is unreachable instead of claiming there is no backup', () => {
    render(<AutoBackupStatus backup={neverBackedUp({ folder_available: false })} />);

    expect(screen.getByText('folderUnavailable')).toBeInTheDocument();
    expect(screen.queryByText('noBackupYet')).not.toBeInTheDocument();
  });

  it('keeps the failure notice next to the unreachable-folder line', () => {
    render(
      <AutoBackupStatus
        backup={neverBackedUp({
          folder_available: false,
          consecutive_failures: 2,
          last_error_code: 'backup_dir_invalid',
        })}
      />,
    );

    expect(screen.getByText('folderUnavailable')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('still says "no backup yet" when the folder is readable and empty', () => {
    render(<AutoBackupStatus backup={neverBackedUp()} />);

    expect(screen.getByText('noBackupYet')).toBeInTheDocument();
    expect(screen.queryByText('folderUnavailable')).not.toBeInTheDocument();
  });
});
