/** @vitest-environment jsdom */
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api';
import type { ImaItemCounts, ImaStatus } from '@/services/wiki/ima';

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), message: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMock }));

const imaMock = vi.hoisted(() => ({
  getImaStatus: vi.fn(),
  saveImaCredentials: vi.fn(),
  deleteImaCredentials: vi.fn(),
  listImaLibraries: vi.fn(),
  saveImaSelection: vi.fn(),
  startImaSync: vi.fn(),
  pauseImaSync: vi.fn(),
  resumeImaSync: vi.fn(),
  retryFailedImaItems: vi.fn(),
  compileImaImports: vi.fn(),
  listImaItems: vi.fn(),
}));
vi.mock('@/services/wiki/ima', () => imaMock);

import { WikiAgentScopeProvider } from '../../WikiAgentScopeContext';
import ImaSourceCard from '../ImaSourceCard';
import { IMA_POLL_INTERVAL_MS } from '../useImaSync';

const NO_COUNTS: ImaItemCounts = {
  total: 0,
  synced: 0,
  pending: 0,
  failed: 0,
  unsupported: 0,
  too_large: 0,
  blocked: 0,
  dismissed: 0,
  remote_deleted: 0,
  duplicate: 0,
  partial: 0,
};

function makeStatus(overrides: Partial<ImaStatus> = {}): ImaStatus {
  return {
    connected: true,
    account_hint: 'abcd…wxyz',
    needs_reauth: false,
    knowledge_bases: [],
    include_notes: true,
    job: { state: 'none', next_run_at: null },
    phase: 'idle',
    backfill_complete: false,
    last_run_at: null,
    last_error_kind: '',
    notes_unavailable: false,
    counts: NO_COUNTS,
    total_chars: 0,
    ...overrides,
  };
}

const SYNCING = makeStatus({
  knowledge_bases: [{ id: 'kb1', name: 'Research' }],
  job: { state: 'active', next_run_at: null },
  phase: 'fetch',
  counts: { ...NO_COUNTS, total: 10, pending: 4, synced: 6, failed: 1, partial: 2 },
  total_chars: 12_000,
});

function renderCard() {
  return render(
    <WikiAgentScopeProvider agentScopeId={null} scopeRevision={0} scopeLabel="default">
      <ImaSourceCard />
    </WikiAgentScopeProvider>,
  );
}

beforeEach(() => {
  Object.values(imaMock).forEach((mock) => mock.mockReset());
  Object.values(toastMock).forEach((mock) => mock.mockReset());
  imaMock.listImaLibraries.mockResolvedValue([
    { id: 'kb1', name: 'Research' },
    { id: 'kb2', name: 'Recipes' },
  ]);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('ImaSourceCard connect', () => {
  it('asks for the credentials first and sends them trimmed, then moves on to the library choice', async () => {
    imaMock.getImaStatus.mockResolvedValue(makeStatus({ connected: false }));
    imaMock.saveImaCredentials.mockResolvedValue(makeStatus());
    renderCard();

    await userEvent.type(await screen.findByLabelText('connect.clientIdLabel'), '  client-1 ');
    await userEvent.type(screen.getByLabelText('connect.apiKeyLabel'), ' secret-key ');
    await userEvent.click(screen.getByRole('button', { name: 'connect.submit' }));

    expect(imaMock.saveImaCredentials).toHaveBeenCalledWith({ client_id: 'client-1', api_key: 'secret-key' }, null);
    expect(await screen.findByText('libraries.hint')).toBeInTheDocument();
    expect(toastMock.success).toHaveBeenCalledWith('connect.success');
  });

  it('keeps the form and the typed key, shows plain-language copy and never the server text', async () => {
    imaMock.getImaStatus.mockResolvedValue(makeStatus({ connected: false }));
    imaMock.saveImaCredentials.mockRejectedValue(
      new ApiError('ima rejected the credentials', 400, [], undefined, 'ima_auth_failed'),
    );
    renderCard();

    await userEvent.type(await screen.findByLabelText('connect.clientIdLabel'), 'client-1');
    await userEvent.type(screen.getByLabelText('connect.apiKeyLabel'), 'bad-key');
    await userEvent.click(screen.getByRole('button', { name: 'connect.submit' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('errors.ima_auth_failed');
    expect(screen.queryByText(/ima rejected/)).not.toBeInTheDocument();
    expect(screen.getByLabelText('connect.apiKeyLabel')).toHaveValue('bad-key');
  });

  it('does not allow submitting an empty form', async () => {
    imaMock.getImaStatus.mockResolvedValue(makeStatus({ connected: false }));
    renderCard();

    expect(await screen.findByRole('button', { name: 'connect.submit' })).toBeDisabled();
  });

  it('explains that the saved key was refused and asks for it again', async () => {
    imaMock.getImaStatus.mockResolvedValue(
      makeStatus({ needs_reauth: true, job: { state: 'paused', next_run_at: null } }),
    );
    renderCard();

    expect(await screen.findByText('connect.reconnectNotice')).toBeInTheDocument();
    expect(screen.getByText('badge.needsReconnect')).toBeInTheDocument();
  });
});

describe('ImaSourceCard choose and start', () => {
  it('saves the chosen libraries, starts the import with the reader locale and shows the running sync', async () => {
    imaMock.getImaStatus.mockResolvedValue(makeStatus());
    imaMock.saveImaSelection.mockResolvedValue(makeStatus());
    imaMock.startImaSync.mockResolvedValue(SYNCING);
    renderCard();

    await userEvent.click(await screen.findByLabelText('Research'));
    await userEvent.click(screen.getByRole('button', { name: 'libraries.start' }));

    expect(imaMock.saveImaSelection).toHaveBeenCalledWith({ library_ids: ['kb1'], include_notes: true }, null);
    expect(imaMock.startImaSync).toHaveBeenCalledWith('en', null);
    expect(await screen.findByText('mode.importing')).toBeInTheDocument();
    expect(toastMock.success).toHaveBeenCalledWith('libraries.started');
  });

  it('keeps the start button off until something is chosen', async () => {
    imaMock.getImaStatus.mockResolvedValue(makeStatus({ include_notes: false }));
    renderCard();

    expect(await screen.findByRole('button', { name: 'libraries.start' })).toBeDisabled();
    await userEvent.click(screen.getByLabelText('Recipes'));
    expect(screen.getByRole('button', { name: 'libraries.start' })).toBeEnabled();
  });

  it('shows a reload action when ima cannot be reached for the library list', async () => {
    imaMock.getImaStatus.mockResolvedValue(makeStatus());
    imaMock.listImaLibraries.mockRejectedValueOnce(new ApiError('boom', 502, [], undefined, 'ima_unreachable'));
    renderCard();

    expect(await screen.findByText('errors.ima_unreachable')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'libraries.reload' }));
    expect(await screen.findByLabelText('Research')).toBeInTheDocument();
  });
});

describe('ImaSourceCard sync', () => {
  it('reports honest outcome counts instead of one reassuring number', async () => {
    imaMock.getImaStatus.mockResolvedValue(SYNCING);
    renderCard();

    expect(await screen.findByText('mode.importing')).toBeInTheDocument();
    for (const key of ['stats.imported', 'stats.pending', 'stats.failed', 'stats.partial']) {
      expect(screen.getByText(key)).toBeInTheDocument();
    }
    expect(screen.getByText('mode.progress')).toBeInTheDocument();
    expect(screen.getByText('badge.syncing')).toBeInTheDocument();
  });

  it('pauses and resumes, and words a failure plainly', async () => {
    imaMock.getImaStatus.mockResolvedValue(SYNCING);
    imaMock.pauseImaSync.mockResolvedValue({ ...SYNCING, job: { state: 'paused', next_run_at: null } });
    imaMock.resumeImaSync.mockRejectedValue(new ApiError('cron limit', 409, [], undefined, 'sync_unavailable'));
    renderCard();

    await userEvent.click(await screen.findByRole('button', { name: 'actions.pause' }));
    expect(imaMock.pauseImaSync).toHaveBeenCalledWith(null);
    expect(await screen.findByText('badge.paused')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'actions.resume' }));
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('errors.sync_unavailable'));
  });

  it('builds knowledge only when asked and says how many documents were queued', async () => {
    imaMock.getImaStatus.mockResolvedValue(SYNCING);
    imaMock.compileImaImports.mockResolvedValueOnce(6).mockResolvedValueOnce(0);
    renderCard();

    await userEvent.click(await screen.findByRole('button', { name: 'compile.action' }));
    expect(imaMock.compileImaImports).toHaveBeenCalledWith(null);
    await waitFor(() => expect(toastMock.success).toHaveBeenCalledWith('compile.queued'));

    await userEvent.click(screen.getByRole('button', { name: 'compile.action' }));
    await waitFor(() => expect(toastMock.message).toHaveBeenCalledWith('compile.nothing'));
  });

  it('says so when the dedup review blocks building knowledge', async () => {
    imaMock.getImaStatus.mockResolvedValue(SYNCING);
    imaMock.compileImaImports.mockRejectedValue(new ApiError('resolve', 409, [], undefined, 'dedup_review_required'));
    renderCard();

    await userEvent.click(await screen.findByRole('button', { name: 'compile.action' }));
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('errors.dedup_review_required'));
  });

  it('reopens the library choice with the current selection, and can back out', async () => {
    imaMock.getImaStatus.mockResolvedValue(SYNCING);
    renderCard();

    await userEvent.click(await screen.findByRole('button', { name: 'manage.changeSelection' }));
    expect(await screen.findByLabelText('Research')).toBeChecked();
    await userEvent.click(screen.getByRole('button', { name: 'common.cancel' }));
    expect(await screen.findByText('mode.importing')).toBeInTheDocument();
  });

  it('disconnects only after confirmation', async () => {
    imaMock.getImaStatus.mockResolvedValue(SYNCING);
    imaMock.deleteImaCredentials.mockResolvedValue(makeStatus({ connected: false }));
    renderCard();

    await userEvent.click(await screen.findByRole('button', { name: 'manage.disconnect' }));
    expect(imaMock.deleteImaCredentials).not.toHaveBeenCalled();
    await userEvent.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'manage.disconnectConfirm' }),
    );

    expect(imaMock.deleteImaCredentials).toHaveBeenCalledWith(null);
    expect(await screen.findByLabelText('connect.clientIdLabel')).toBeInTheDocument();
  });
});

describe('ImaSourceCard report', () => {
  it('lists what needs attention in plain words and re-queues failures', async () => {
    imaMock.getImaStatus.mockResolvedValue(SYNCING);
    imaMock.listImaItems.mockResolvedValue([
      {
        title: 'Quarterly.xlsx',
        folder_path: 'Finance',
        container_name: 'Research',
        media_kind: 'excel',
        status: 'failed',
        reason: 'transient',
        notes: [],
      },
      {
        title: 'Movie.mp4',
        folder_path: '',
        container_name: 'Research',
        media_kind: 'video',
        status: 'unsupported',
        reason: 'surprising_new_code',
        notes: [],
      },
    ]);
    imaMock.retryFailedImaItems.mockResolvedValue(1);
    renderCard();

    await userEvent.click(await screen.findByRole('button', { name: 'actions.viewDetails' }));
    expect(imaMock.listImaItems).toHaveBeenCalledWith('attention', null);
    expect(await screen.findByText('Quarterly.xlsx')).toBeInTheDocument();
    expect(screen.getByText('reasons.transient')).toBeInTheDocument();
    expect(screen.getByText('reasons.generic')).toBeInTheDocument();
    expect(screen.queryByText(/surprising_new_code/)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'report.retryFailed' }));
    expect(imaMock.retryFailedImaItems).toHaveBeenCalledWith(null);
    await waitFor(() => expect(toastMock.success).toHaveBeenCalledWith('report.retried'));
  });

  it('switches to the simplified bucket and explains each simplification', async () => {
    imaMock.getImaStatus.mockResolvedValue(SYNCING);
    imaMock.listImaItems.mockImplementation(async (bucket: string) =>
      bucket === 'lossy'
        ? [
            {
              title: 'Article',
              folder_path: '',
              container_name: 'Research',
              media_kind: 'wechat',
              status: 'synced',
              reason: '',
              notes: ['images_remote', 'not_a_known_note'],
            },
          ]
        : [],
    );
    renderCard();

    await userEvent.click(await screen.findByRole('button', { name: 'actions.viewDetails' }));
    await userEvent.click(await screen.findByRole('tab', { name: /report\.tabs\.lossy/ }));

    expect(await screen.findByText('Article')).toBeInTheDocument();
    expect(screen.getByText('notes.images_remote')).toBeInTheDocument();
    expect(screen.queryByText(/not_a_known_note/)).not.toBeInTheDocument();
  });
});

describe('ImaSourceCard polling', () => {
  it('follows a running import and stops once it is up to date', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    imaMock.getImaStatus
      .mockResolvedValueOnce(SYNCING)
      .mockResolvedValueOnce({ ...SYNCING, counts: { ...SYNCING.counts, pending: 1, synced: 9 } })
      .mockResolvedValue({
        ...SYNCING,
        phase: 'idle',
        backfill_complete: true,
        counts: { ...SYNCING.counts, pending: 0, synced: 10 },
      });
    renderCard();

    expect(await screen.findByText('mode.importing')).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(IMA_POLL_INTERVAL_MS);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(IMA_POLL_INTERVAL_MS);
    });
    expect(await screen.findByText('mode.upToDate')).toBeInTheDocument();
    expect(imaMock.getImaStatus).toHaveBeenCalledTimes(3);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(IMA_POLL_INTERVAL_MS * 3);
    });
    expect(imaMock.getImaStatus).toHaveBeenCalledTimes(3);
  });

  it('does not poll an idle card', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    imaMock.getImaStatus.mockResolvedValue(makeStatus({ connected: false }));
    renderCard();

    await screen.findByLabelText('connect.clientIdLabel');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(IMA_POLL_INTERVAL_MS * 3);
    });
    expect(imaMock.getImaStatus).toHaveBeenCalledTimes(1);
  });

  it('offers a retry when the status cannot be read at all', async () => {
    imaMock.getImaStatus
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValue(makeStatus({ connected: false }));
    renderCard();

    expect(await screen.findByText('loadError')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'libraries.reload' }));
    expect(await screen.findByLabelText('connect.clientIdLabel')).toBeInTheDocument();
  });
});
