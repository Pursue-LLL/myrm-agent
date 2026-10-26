/** @vitest-environment jsdom */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api';
import { makeStatus, renderCard, SYNCING, installImaCardLifecycle } from './imaFixtures';
import { imaMock, toastMock } from './imaMocks';

vi.mock('sonner', async () => ({ toast: (await import('./imaMocks')).toastMock }));
vi.mock('@/services/wiki/ima', async () => (await import('./imaMocks')).imaMock);

installImaCardLifecycle();

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

  it('links to the ima page where the credentials are created, opening outside the app safely', async () => {
    imaMock.getImaStatus.mockResolvedValue(makeStatus({ connected: false }));
    renderCard();

    const link = await screen.findByRole('link', { name: 'connect.getCredentials' });
    expect(link).toHaveAttribute('href', 'https://ima.qq.com/agent-interface');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
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

  it('lets a wrong account be disconnected before anything was imported', async () => {
    imaMock.getImaStatus.mockResolvedValue(makeStatus());
    imaMock.deleteImaCredentials.mockResolvedValue(makeStatus({ connected: false }));
    renderCard();

    await userEvent.click(await screen.findByRole('button', { name: 'manage.disconnect' }));
    await userEvent.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'manage.disconnectConfirm' }),
    );

    expect(imaMock.deleteImaCredentials).toHaveBeenCalledWith(null);
    expect(await screen.findByLabelText('connect.clientIdLabel')).toBeInTheDocument();
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

  it('compiles only when asked and says how many documents were queued', async () => {
    imaMock.getImaStatus.mockResolvedValue(SYNCING);
    imaMock.compileImaImports.mockResolvedValueOnce(6).mockResolvedValueOnce(0);
    renderCard();

    await userEvent.click(await screen.findByRole('button', { name: 'compile.action' }));
    expect(imaMock.compileImaImports).toHaveBeenCalledWith(null);
    await waitFor(() => expect(toastMock.success).toHaveBeenCalledWith('compile.queued'));

    await userEvent.click(screen.getByRole('button', { name: 'compile.action' }));
    await waitFor(() => expect(toastMock.message).toHaveBeenCalledWith('compile.nothing'));
  });

  it('says so when the dedup review blocks compiling', async () => {
    imaMock.getImaStatus.mockResolvedValue(SYNCING);
    imaMock.compileImaImports.mockRejectedValue(new ApiError('resolve', 409, [], undefined, 'dedup_review_required'));
    renderCard();

    await userEvent.click(await screen.findByRole('button', { name: 'compile.action' }));
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('errors.dedup_review_required'));
  });

  it('says how later documents get compiled, following the shared auto-compile switch and the first import', async () => {
    const settled = { ...SYNCING, phase: 'idle' as const, backfill_complete: true };
    imaMock.getImaStatus.mockResolvedValueOnce(settled);
    const { unmount } = renderCard();
    expect(await screen.findByText('compile.autoOn')).toBeInTheDocument();
    unmount();

    imaMock.getImaStatus.mockResolvedValueOnce({ ...settled, auto_compile: false });
    const second = renderCard();
    expect(await screen.findByText('compile.autoOff')).toBeInTheDocument();
    second.unmount();

    imaMock.getImaStatus.mockResolvedValueOnce(SYNCING);
    renderCard();
    expect(await screen.findByText('compile.autoPending')).toBeInTheDocument();
  });

  it('shows what the user removed and tells a failed run apart from a slow one', async () => {
    imaMock.getImaStatus.mockResolvedValue({
      ...SYNCING,
      last_error_kind: 'internal',
      counts: { ...SYNCING.counts, dismissed: 3 },
    });
    renderCard();

    expect(await screen.findByText('stats.dismissed')).toBeInTheDocument();
    expect(screen.getByText('notices.internal')).toBeInTheDocument();
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
