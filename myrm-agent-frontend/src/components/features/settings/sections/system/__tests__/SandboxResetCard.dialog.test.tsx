/** @vitest-environment jsdom */
/**
 * [INPUT]
 * - @/components/features/settings/sections/system/SandboxResetCard
 * - @/components/features/app-shell/confirm-dialog (real, not mocked)
 * - @/lib/api: apiRequest
 *
 * [OUTPUT]
 * - Test suite for the confirmation step of the cloud sandbox "reset environment" card
 *
 * [POS]
 * Pins the path a user actually takes: the reset button only asks, cancelling sends nothing, and once confirmed a
 * second click cannot start a second container swap while the first request is still in flight. The sibling
 * suite replaces the dialog with a stub to pin the messages; this one keeps the real dialog.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SandboxResetCard from '../SandboxResetCard';
import { apiRequest } from '@/lib/api';
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

function deferred<T>() {
  let resolve: (value: T) => void = () => undefined;
  const promise = new Promise<T>((settle) => {
    resolve = settle;
  });
  return { promise, resolve };
}

describe('SandboxResetCard confirmation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('only asks when the reset button is pressed and sends nothing until the user confirms', async () => {
    render(<SandboxResetCard />);
    expect(screen.queryByText('confirmTitle')).toBeNull();

    fireEvent.click(screen.getByText('button'));

    expect(await screen.findByText('confirmTitle')).toBeInTheDocument();
    expect(screen.getByText('confirmDescription')).toBeInTheDocument();
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('sends nothing and closes the dialog when the user cancels', async () => {
    render(<SandboxResetCard />);
    fireEvent.click(screen.getByText('button'));
    await screen.findByText('confirmTitle');

    fireEvent.click(screen.getByTestId('confirm-dialog-cancel'));

    await waitFor(() => expect(screen.queryByText('confirmTitle')).toBeNull());
    expect(apiRequest).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('starts one swap only, however often confirm is pressed while the request is in flight', async () => {
    const pending = deferred<{ status: string }>();
    vi.mocked(apiRequest).mockReturnValue(pending.promise);
    render(<SandboxResetCard />);
    fireEvent.click(screen.getByText('button'));
    await screen.findByText('confirmTitle');

    fireEvent.click(screen.getByTestId('confirm-dialog-confirm'));
    fireEvent.click(screen.getByTestId('confirm-dialog-confirm'));

    expect(apiRequest).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('confirm-dialog-confirm')).toBeDisabled();
    expect(screen.getByTestId('confirm-dialog-cancel')).toBeDisabled();
    expect(screen.getByText('button').closest('button')).toBeDisabled();

    pending.resolve({ status: 'accepted' });

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('success'));
    await waitFor(() => expect(screen.queryByText('confirmTitle')).toBeNull());
    expect(apiRequest).toHaveBeenCalledTimes(1);
    expect(screen.getByText('button').closest('button')).toBeEnabled();
  });
});
