/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMock }));

import MemoryBackupSection from '../MemoryBackupSection';

function reply(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response;
}

/** The list answers no backups; the create endpoint answers `created`. */
function serve(created: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => (url.endsWith('/create') ? reply(created) : reply({ backups: [] }))),
  );
}

async function createBackup() {
  render(<MemoryBackupSection />);
  await userEvent.click(screen.getByText('createBackup'));
}

beforeEach(() => {
  toastMock.success.mockReset();
  toastMock.error.mockReset();
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

describe('MemoryBackupSection manual backup', () => {
  it('names the refusal caused by memories left under a previous embedding model', async () => {
    serve({
      success: false,
      error: 'Backup would be incomplete, nothing was saved: memories under a previous embedding model (3)',
      error_code: 'previous_model',
      duration_ms: 3,
    });

    await createBackup();

    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('createErrorPreviousModel'));
    expect(toastMock.error).toHaveBeenCalledTimes(1);
    expect(toastMock.success).not.toHaveBeenCalled();
  });

  it('shows the generic failure for a refusal that carries no code', async () => {
    serve({ success: false, error: 'Backup would be incomplete, nothing was saved: semantic (1 of 2)', duration_ms: 3 });

    await createBackup();

    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('createError'));
    expect(toastMock.error).toHaveBeenCalledTimes(1);
  });

  it('confirms a created backup', async () => {
    serve({ success: true, backup_id: 'memory_20261108_000000_deadbeef', duration_ms: 3 });

    await createBackup();

    await waitFor(() => expect(toastMock.success).toHaveBeenCalledWith('createSuccess'));
    expect(toastMock.error).not.toHaveBeenCalled();
  });
});
