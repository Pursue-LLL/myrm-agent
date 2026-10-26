/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { toast } from '@/hooks/shared/useToast';
import { confirmAction } from '@/lib/app-dialog';
import { cleanupCheckpoints, listCheckpoints } from '@/services/checkpoint';
import CheckpointList from '../CheckpointList';

const stableT = (key: string, values?: { deleted?: number }) =>
  values?.deleted === undefined ? key : `${key}:${values.deleted}`;
vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('@/lib/app-dialog', () => ({ confirmAction: vi.fn() }));
vi.mock('@/hooks/shared/useToast', () => ({ toast: { success: vi.fn() } }));
vi.mock('@/services/checkpoint', () => ({
  listCheckpoints: vi.fn(),
  deleteCheckpoint: vi.fn(),
  cleanupCheckpoints: vi.fn(),
}));

const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

describe('CheckpointList cleanup', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listCheckpoints).mockResolvedValue({ checkpoints: [], total: 0 });
    vi.mocked(cleanupCheckpoints).mockResolvedValue({ deleted: 3 } as Awaited<ReturnType<typeof cleanupCheckpoints>>);
  });

  it('clears old checkpoints only after the user confirms, then reloads the list', async () => {
    vi.mocked(confirmAction).mockResolvedValue(true);
    render(<CheckpointList />);
    await waitFor(() => expect(listCheckpoints).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole('button', { name: /cleanup/ }));

    await waitFor(() => expect(cleanupCheckpoints).toHaveBeenCalledExactlyOnceWith(7));
    expect(confirmAction).toHaveBeenCalledExactlyOnceWith({
      variant: 'warning',
      description: 'confirmCleanup',
      confirmText: 'cleanup',
    });
    await waitFor(() => expect(listCheckpoints).toHaveBeenCalledTimes(2));
    expect(toast.success).toHaveBeenCalledWith('cleanupSuccess:3');
  });

  it('leaves everything alone when the user declines', async () => {
    vi.mocked(confirmAction).mockResolvedValue(false);
    render(<CheckpointList />);
    await waitFor(() => expect(listCheckpoints).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole('button', { name: /cleanup/ }));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledTimes(1));
    await settle();

    expect(cleanupCheckpoints).not.toHaveBeenCalled();
    expect(listCheckpoints).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: /cleanup/ })).toBeEnabled();
  });
});
