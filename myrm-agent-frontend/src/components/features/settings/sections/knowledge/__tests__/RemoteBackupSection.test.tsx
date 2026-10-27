/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const stableT = (key: string) => key;

const mocks = vi.hoisted(() => ({
  fetchWithTimeout: vi.fn(),
  saved: undefined as unknown,
  set: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('@/services/config', () => ({
  getConfigSyncManager: () => ({ get: () => mocks.saved, set: mocks.set }),
}));

vi.mock('@/lib/api', () => ({ fetchWithTimeout: mocks.fetchWithTimeout }));
vi.mock('sonner', () => ({ toast: mocks.toast }));

import RemoteBackupSection from '../RemoteBackupSection';
import { DEFAULT_CONFIG } from '../remote-backup/remoteBackupConfig';

const SERVER_WORDING = 'Remote upload failed after retries';
const HEALTHY = {
  last_success_at: '2026-10-26T12:00:00Z',
  last_attempt_at: null,
  last_error_code: null,
  consecutive_failures: 0,
};
const FILE_A = {
  file_name: 'myrm.20261026120000.laptop.a1b2c3d4.darwin.json.gz',
  modified_time: '2026-10-26T12:00:00Z',
  size_bytes: 12600,
};
const FILE_B = {
  file_name: 'myrm.20261025120000.desktop.a1b2c3d4.linux.json.gz',
  modified_time: '2026-10-25T12:00:00Z',
  size_bytes: 2048,
};

const configured = (patch: Record<string, unknown> = {}) => ({
  ...DEFAULT_CONFIG,
  enabled: true,
  webdav: { ...DEFAULT_CONFIG.webdav, host: 'https://dav.example.com', username: 'me', password: 'secret' },
  ...patch,
});

function reply(body: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

type Route = (url: string, init?: RequestInit) => Response | Promise<Response> | undefined;

/** Serves every call from `routes`, falling back to a healthy answer; remembers the calls for assertions. */
function serve(routes: Record<string, Route | Response> = {}) {
  mocks.fetchWithTimeout.mockImplementation(async (url: string, init?: RequestInit) => {
    const route = routes[url.replace('/memory/backup/remote/', '')];
    const answer = typeof route === 'function' ? route(url, init) : route;
    if (answer) {
      return answer;
    }
    if (url.endsWith('/auto-status')) {
      return reply(HEALTHY);
    }
    if (url.endsWith('/list')) {
      return reply({ files: [FILE_A] });
    }
    if (url.endsWith('/check-connection')) {
      return reply({ connected: true });
    }
    return reply({ success: true });
  });
}

const callsTo = (path: string) =>
  mocks.fetchWithTimeout.mock.calls.filter(([url]) => (url as string).endsWith(`/${path}`));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.set.mockReset();
  mocks.saved = undefined;
  serve();
});

describe('before the cloud backup is switched on', () => {
  it('says up front what the file does and does not protect', () => {
    render(<RemoteBackupSection />);

    expect(screen.getByText('notePlain')).toBeInTheDocument();
    expect(screen.getByText('noteScope')).toBeInTheDocument();
    expect(screen.getByRole('switch')).not.toBeChecked();
  });

  it('reaches out to nothing', () => {
    render(<RemoteBackupSection />);

    expect(mocks.fetchWithTimeout).not.toHaveBeenCalled();
  });

  it('shows the form once it is switched on', async () => {
    render(<RemoteBackupSection />);

    await userEvent.setup().click(screen.getByRole('switch', { name: 'enabled' }));

    expect(screen.getByLabelText('webdavHost')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'testConnection' })).toBeInTheDocument();
    expect(screen.getByText('listIdle')).toBeInTheDocument();
  });
});

describe('when it was set up before', () => {
  it('lists the backups of the saved storage, not of an empty form', async () => {
    mocks.saved = configured();
    render(<RemoteBackupSection />);

    expect(await screen.findByText('12.3 KB · laptop')).toBeInTheDocument();
    const [, init] = callsTo('list')[0];
    expect(JSON.parse((init as RequestInit).body as string).webdav.host).toBe('https://dav.example.com');
    expect(callsTo('auto-status')).toHaveLength(1);
  });

  it('does not list a storage that has no address yet', async () => {
    mocks.saved = { ...DEFAULT_CONFIG, enabled: true };
    render(<RemoteBackupSection />);

    expect(await screen.findByText('listIdle')).toBeInTheDocument();
    expect(callsTo('list')).toHaveLength(0);
  });

  it('shows the last backup and, when the schedule is failing, why', async () => {
    mocks.saved = configured({ autoSync: true });
    serve({
      'auto-status': reply({ ...HEALTHY, last_error_code: 'upload', consecutive_failures: 3 }),
    });
    render(<RemoteBackupSection />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('statusFailing');
    expect(alert).toHaveTextContent('errorCodes.upload');
  });

  it('shows a saved frequency the card does not offer as the nearest one it does', async () => {
    mocks.saved = configured({ autoSync: true, syncInterval: 5 });
    render(<RemoteBackupSection />);

    expect(await screen.findByRole('radio', { name: 'intervalOptions.hourly' })).toBeChecked();
  });
});

describe('a storage that cannot be read', () => {
  it('is not shown as having no backups, and can be read again', async () => {
    const user = userEvent.setup();
    mocks.saved = configured();
    serve({ list: reply({ detail: 'refused' }, 502) });
    render(<RemoteBackupSection />);

    expect(await screen.findByText('listError')).toBeInTheDocument();
    expect(screen.queryByText('noRemoteFiles')).not.toBeInTheDocument();

    serve();
    await user.click(screen.getByRole('button', { name: 'retry' }));

    expect(await screen.findByText('12.3 KB · laptop')).toBeInTheDocument();
    expect(screen.queryByText('listError')).not.toBeInTheDocument();
  });

  it('keeps the newest answer when an older one arrives late', async () => {
    const user = userEvent.setup();
    mocks.saved = configured();
    let releaseFirst: (response: Response) => void = () => undefined;
    const answers = [
      new Promise<Response>((resolve) => {
        releaseFirst = resolve;
      }),
      Promise.resolve(reply({ files: [FILE_B] })),
    ];
    serve({ list: () => answers.shift() });
    render(<RemoteBackupSection />);

    await user.click(await screen.findByRole('button', { name: 'testConnection' }));
    expect(await screen.findByText('2.0 KB · desktop')).toBeInTheDocument();

    await act(async () => {
      releaseFirst(reply({ files: [FILE_A] }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(callsTo('list')).toHaveLength(2);
    expect(screen.getByText('2.0 KB · desktop')).toBeInTheDocument();
    expect(screen.queryByText('12.3 KB · laptop')).not.toBeInTheDocument();
  });
});

describe('backing up now', () => {
  it('tells a failure by its localized reason, never by the server wording', async () => {
    const user = userEvent.setup();
    mocks.saved = configured();
    serve({ trigger: reply({ success: false, error: SERVER_WORDING, error_code: 'upload' }) });
    render(<RemoteBackupSection />);

    await user.click(await screen.findByRole('button', { name: 'triggerBackup' }));

    await waitFor(() => expect(mocks.toast.error).toHaveBeenCalledWith('errorCodes.upload'));
    expect(mocks.toast.error).not.toHaveBeenCalledWith(SERVER_WORDING);
    expect(mocks.toast.success).not.toHaveBeenCalled();
  });

  it('says the same for a backup that is already running', async () => {
    const user = userEvent.setup();
    mocks.saved = configured();
    serve({ trigger: reply({ success: false, error: 'Backup already in progress', error_code: 'busy' }) });
    render(<RemoteBackupSection />);

    await user.click(await screen.findByRole('button', { name: 'triggerBackup' }));

    await waitFor(() => expect(mocks.toast.error).toHaveBeenCalledWith('errorCodes.busy'));
  });

  it('refreshes the list and the status after a success', async () => {
    const user = userEvent.setup();
    mocks.saved = configured();
    render(<RemoteBackupSection />);
    await screen.findByText('12.3 KB · laptop');

    await user.click(screen.getByRole('button', { name: 'triggerBackup' }));

    await waitFor(() => expect(mocks.toast.success).toHaveBeenCalledWith('backupSuccess'));
    await waitFor(() => expect(callsTo('list')).toHaveLength(2));
    expect(callsTo('auto-status')).toHaveLength(2);
  });

  it('falls back to a generic failure when the request itself failed', async () => {
    const user = userEvent.setup();
    mocks.saved = configured();
    serve({
      trigger: () => {
        throw new Error('network down');
      },
    });
    render(<RemoteBackupSection />);

    await user.click(await screen.findByRole('button', { name: 'triggerBackup' }));

    await waitFor(() => expect(mocks.toast.error).toHaveBeenCalledWith('backupError'));
  });
});

describe('deleting and restoring', () => {
  it('says so when a backup could not be deleted', async () => {
    const user = userEvent.setup();
    mocks.saved = configured();
    serve({ delete: reply({ success: false }) });
    render(<RemoteBackupSection />);
    await screen.findByText('12.3 KB · laptop');

    await user.click(screen.getByRole('button', { name: 'deleteFromCloud' }));
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'deleteFromCloud' }));

    await waitFor(() => expect(mocks.toast.error).toHaveBeenCalledWith('deleteFailed'));
    expect(mocks.toast.success).not.toHaveBeenCalled();
    expect(callsTo('list')).toHaveLength(1);
  });

  it('lists again after a backup was deleted', async () => {
    const user = userEvent.setup();
    mocks.saved = configured();
    render(<RemoteBackupSection />);
    await screen.findByText('12.3 KB · laptop');

    await user.click(screen.getByRole('button', { name: 'deleteFromCloud' }));
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'deleteFromCloud' }));

    await waitFor(() => expect(mocks.toast.success).toHaveBeenCalledWith('deleteSuccess'));
    await waitFor(() => expect(callsTo('list')).toHaveLength(2));
    expect(JSON.parse(callsTo('delete')[0][1].body as string).file_name).toBe(FILE_A.file_name);
  });

  it('tells a restore that failed in localized words only', async () => {
    const user = userEvent.setup();
    mocks.saved = configured();
    serve({ restore: reply({ success: false, error: 'Failed to download backup.json.gz' }) });
    render(<RemoteBackupSection />);
    await screen.findByText('12.3 KB · laptop');

    await user.click(screen.getByRole('button', { name: 'restoreFromCloud' }));
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'restoreFromCloud' }));

    await waitFor(() => expect(mocks.toast.error).toHaveBeenCalledWith('restoreError'));
  });
});

describe('saving', () => {
  it('stores the settings as shown, with a frequency the server can keep', async () => {
    const user = userEvent.setup();
    mocks.saved = configured({ autoSync: true, syncInterval: 5, maxBackups: 0 });
    render(<RemoteBackupSection />);

    await user.click(await screen.findByRole('button', { name: 'save' }));

    expect(mocks.set).toHaveBeenCalledWith(
      'backupSync',
      expect.objectContaining({ enabled: true, autoSync: true, syncInterval: 60, maxBackups: 1 }),
    );
    expect(mocks.toast.success).toHaveBeenCalledWith('saveSuccess');
  });

  it('says so when the settings could not be stored', async () => {
    const user = userEvent.setup();
    mocks.saved = configured();
    mocks.set.mockImplementation(() => {
      throw new Error('storage full');
    });
    render(<RemoteBackupSection />);

    await user.click(await screen.findByRole('button', { name: 'save' }));

    expect(mocks.toast.error).toHaveBeenCalledWith('saveFailed');
  });
});

describe('the connection test', () => {
  it('reads the storage after it connected', async () => {
    const user = userEvent.setup();
    mocks.saved = configured();
    render(<RemoteBackupSection />);
    await screen.findByText('12.3 KB · laptop');

    await user.click(screen.getByRole('button', { name: 'testConnection' }));

    await waitFor(() => expect(mocks.toast.success).toHaveBeenCalledWith('connectionSuccess'));
    await waitFor(() => expect(callsTo('list')).toHaveLength(2));
  });

  it('says it failed when the server cannot connect', async () => {
    const user = userEvent.setup();
    mocks.saved = configured();
    serve({ 'check-connection': reply({ connected: false }) });
    render(<RemoteBackupSection />);

    await user.click(await screen.findByRole('button', { name: 'testConnection' }));

    await waitFor(() => expect(mocks.toast.error).toHaveBeenCalledWith('connectionFailed'));
    expect(callsTo('list')).toHaveLength(1);
  });
});
