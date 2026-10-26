/** @vitest-environment jsdom */
import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api';
import { IMA_POLL_INTERVAL_MS, IMA_WATCH_AFTER_SYNC_NOW_MS } from '../useImaSync';
import { makeStatus, NO_COUNTS, renderCard, SYNCING, UP_TO_DATE, installImaCardLifecycle } from './imaFixtures';
import { imaMock, toastMock } from './imaMocks';

vi.mock('sonner', async () => ({ toast: (await import('./imaMocks')).toastMock }));
vi.mock('@/services/wiki/ima', async () => (await import('./imaMocks')).imaMock);

installImaCardLifecycle();

describe('ImaSourceCard sync now', () => {
  it('tells the user when the next automatic check is and runs it on request without touching the selection', async () => {
    imaMock.getImaStatus.mockResolvedValue(UP_TO_DATE);
    imaMock.startImaSync.mockResolvedValue({ ...UP_TO_DATE, phase: 'fetch' });
    renderCard();

    expect(await screen.findByText('mode.nextCheck')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'actions.syncNow' }));

    expect(imaMock.startImaSync).toHaveBeenCalledWith('en', null);
    expect(imaMock.saveImaSelection).not.toHaveBeenCalled();
    await waitFor(() => expect(toastMock.message).toHaveBeenCalledWith('actions.syncNowStarted'));
    expect(await screen.findByText('mode.importing')).toBeInTheDocument();
  });

  it('keeps watching for the outcome for a while, then goes quiet again', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    imaMock.getImaStatus.mockResolvedValue(UP_TO_DATE);
    imaMock.startImaSync.mockResolvedValue(UP_TO_DATE);
    renderCard();

    await userEvent.click(await screen.findByRole('button', { name: 'actions.syncNow' }));
    const callsAfterClick = imaMock.getImaStatus.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(IMA_POLL_INTERVAL_MS * 2);
    });
    expect(imaMock.getImaStatus.mock.calls.length).toBeGreaterThan(callsAfterClick);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(IMA_WATCH_AFTER_SYNC_NOW_MS);
    });
    const callsWhenQuiet = imaMock.getImaStatus.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(IMA_POLL_INTERVAL_MS * 3);
    });
    expect(imaMock.getImaStatus.mock.calls.length).toBe(callsWhenQuiet);
  });

  it('restarts the observation window on a second click instead of cutting it short', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    imaMock.getImaStatus.mockResolvedValue(UP_TO_DATE);
    imaMock.startImaSync.mockResolvedValue(UP_TO_DATE);
    renderCard();

    await userEvent.click(await screen.findByRole('button', { name: 'actions.syncNow' }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(IMA_WATCH_AFTER_SYNC_NOW_MS * 0.66);
    });
    await userEvent.click(screen.getByRole('button', { name: 'actions.syncNow' }));
    // The first window would have ended by now; the second click keeps the card following the check.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(IMA_WATCH_AFTER_SYNC_NOW_MS * 0.42);
    });
    const callsInsideSecondWindow = imaMock.getImaStatus.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(IMA_POLL_INTERVAL_MS * 2);
    });
    expect(imaMock.getImaStatus.mock.calls.length).toBeGreaterThan(callsInsideSecondWindow);
  });

  it('is not offered while a slice is already reading or importing, nor while paused', async () => {
    imaMock.getImaStatus.mockResolvedValue(SYNCING);
    const { unmount } = renderCard();
    await screen.findByText('mode.importing');
    expect(screen.queryByRole('button', { name: 'actions.syncNow' })).not.toBeInTheDocument();
    unmount();

    imaMock.getImaStatus.mockResolvedValue({ ...UP_TO_DATE, job: { state: 'paused', next_run_at: null } });
    renderCard();
    await screen.findByText('mode.paused');
    expect(screen.queryByRole('button', { name: 'actions.syncNow' })).not.toBeInTheDocument();
  });

  it('words a refusal plainly', async () => {
    imaMock.getImaStatus.mockResolvedValue(UP_TO_DATE);
    imaMock.startImaSync.mockRejectedValue(new ApiError('plan', 409, [], undefined, 'sync_unavailable'));
    renderCard();

    await userEvent.click(await screen.findByRole('button', { name: 'actions.syncNow' }));
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('errors.sync_unavailable'));
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

  it('says when the list is shorter than the count so the numbers never look contradictory', async () => {
    imaMock.getImaStatus.mockResolvedValue(
      makeStatus({
        job: { state: 'active', next_run_at: null },
        counts: { ...NO_COUNTS, total: 400, synced: 100, failed: 300 },
      }),
    );
    imaMock.listImaItems.mockResolvedValue(
      Array.from({ length: 200 }, (_, index) => ({
        title: `Doc ${index}`,
        folder_path: '',
        container_name: 'Research',
        media_kind: 'pdf',
        status: 'failed',
        reason: 'transient',
        notes: [],
      })),
    );
    renderCard();

    await userEvent.click(await screen.findByRole('button', { name: 'actions.viewDetails' }));

    expect(await screen.findByText('report.truncated')).toBeInTheDocument();
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
