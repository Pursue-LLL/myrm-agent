/** @vitest-environment jsdom */
/**
 * [INPUT]
 * - @/components/features/settings/sections/system/SandboxResetCard
 * - @/lib/api: apiRequest, ApiError
 *
 * [OUTPUT]
 * - Test suite for the cloud sandbox "reset environment" card
 *
 * [POS]
 * Pins what the user is told after confirming a reset: the localized messages, never the
 * (English) text the server answers with, and exactly one message per outcome (the request is
 * silent so the global error toast does not stack a second, English one on top), and that the
 * card carries its title once.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SandboxResetCard from '../SandboxResetCard';
import { ApiError, apiRequest } from '@/lib/api';
import { toast } from '@/lib/utils/toast';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiRequest: vi.fn(),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/components/features/app-shell/confirm-dialog', () => ({
  ConfirmDialog: ({ trigger, onConfirm }: { trigger: React.ReactNode; onConfirm: () => void }) => (
    <div>
      {trigger}
      <button type="button" onClick={onConfirm}>
        confirm-reset
      </button>
    </div>
  ),
}));

const SERVER_BUSY_TEXT =
  'Cannot recreate container while an agent run is still in progress. Stop it or wait for it to finish first.';

describe('SandboxResetCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('names the card once; the card is the whole cloud System tab', () => {
    render(<SandboxResetCard />);

    expect(screen.getAllByText('title')).toHaveLength(1);
  });

  it('tells the user in their language that the reset started', async () => {
    vi.mocked(apiRequest).mockResolvedValue({ status: 'accepted' });
    render(<SandboxResetCard />);

    fireEvent.click(screen.getByText('confirm-reset'));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('success'));
    expect(apiRequest).toHaveBeenCalledWith('/system/sandbox/recreate', {
      method: 'POST',
      body: JSON.stringify({ reset_python_env: true }),
      silent: true,
    });
  });

  it('reports a failed reset with the localized message', async () => {
    vi.mocked(apiRequest).mockRejectedValue(new ApiError('Control plane returned 502', 502));
    render(<SandboxResetCard />);

    fireEvent.click(screen.getByText('confirm-reset'));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('failed'));
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('asks the user to let running tasks finish instead of showing the server text', async () => {
    vi.mocked(apiRequest).mockRejectedValue(new ApiError(SERVER_BUSY_TEXT, 409));
    render(<SandboxResetCard />);

    fireEvent.click(screen.getByText('confirm-reset'));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('busy'));
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error).not.toHaveBeenCalledWith(SERVER_BUSY_TEXT);
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('reports a non-API failure (network down) with the generic localized message', async () => {
    vi.mocked(apiRequest).mockRejectedValue(new TypeError('Failed to fetch'));
    render(<SandboxResetCard />);

    fireEvent.click(screen.getByText('confirm-reset'));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('failed'));
  });
});
