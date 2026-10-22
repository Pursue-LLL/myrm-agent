/** Builders shared by the AutoBackup card tests: a server snapshot with sensible defaults, and a refused-request error. */

import { ApiError } from '@/lib/api';
import type { AutoBackup } from '@/services/instanceAutoBackup';

export const DEFAULT_DIR = '/Users/me/.myrm/backups/instance';

export const snapshot = (overrides: Partial<AutoBackup> = {}): AutoBackup => ({
  supported: true,
  enabled: true,
  frequency: 'daily',
  keep: 3,
  directory: DEFAULT_DIR,
  default_directory: true,
  folder_available: true,
  running: false,
  overdue: false,
  last_success_at: '2026-10-12T08:30:00Z',
  last_success_size: 4_300_000,
  consecutive_failures: 0,
  last_error_code: null,
  backups: [
    {
      name: 'myrm-auto-backup-3fa9c2d1-20261012-083000.zip',
      created_at: '2026-10-12T08:30:00Z',
      size_bytes: 4_300_000,
    },
    {
      name: 'myrm-auto-backup-3fa9c2d1-20261011-083000.zip',
      created_at: '2026-10-11T08:30:00Z',
      size_bytes: 4_200_000,
    },
  ],
  ...overrides,
});

export const apiError = (code: string, status = 400) => new ApiError('server wording', status, [], undefined, code);
