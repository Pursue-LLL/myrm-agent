/** @vitest-environment jsdom */
/**
 * [INPUT]
 * - ../RestartNotice
 * - @/lib/instance-archive/restart: planRestart, performRestart
 * - @/lib/api: ApiError
 *
 * [OUTPUT]
 * - Test suite for the "restart to finish" banner
 *
 * [POS]
 * Pins what a failed restart tells the user: a refusal because work is still running (409) is
 * "wait and try again", any other failure is "restart it yourself", and the button stays usable.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { RestartNotice } from '../RestartNotice';
import { ApiError } from '@/lib/api';
import { performRestart } from '@/lib/instance-archive/restart';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/instance-archive/restart', () => ({
  planRestart: () => 'sandbox',
  performRestart: vi.fn(),
}));

const restartNow = () => fireEvent.click(screen.getByRole('button', { name: 'now' }));

describe('RestartNotice', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('asks the user to let running work finish when the sandbox refuses to restart', async () => {
    vi.mocked(performRestart).mockRejectedValue(
      new ApiError('Cannot recreate container while an agent run is still in progress.', 409),
    );
    render(<RestartNotice mode="sandbox" />);

    restartNow();

    expect(await screen.findByText('busy')).toBeInTheDocument();
    expect(screen.queryByText('failed')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'now' })).toBeEnabled();
  });

  it('tells the user to restart it themselves on any other failure', async () => {
    vi.mocked(performRestart).mockRejectedValue(new ApiError('Control plane returned 502', 502));
    render(<RestartNotice mode="sandbox" />);

    restartNow();

    expect(await screen.findByText('failed')).toBeInTheDocument();
    expect(screen.queryByText('busy')).not.toBeInTheDocument();
  });

  it('can be retried after a refusal', async () => {
    vi.mocked(performRestart).mockRejectedValueOnce(new ApiError('busy', 409)).mockResolvedValueOnce(undefined);
    render(<RestartNotice mode="sandbox" />);

    restartNow();
    await screen.findByText('busy');
    restartNow();

    await waitFor(() => expect(performRestart).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByText('busy')).not.toBeInTheDocument());
  });
});
