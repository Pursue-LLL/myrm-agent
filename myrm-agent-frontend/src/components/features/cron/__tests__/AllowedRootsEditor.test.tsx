import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ApiError } from '@/lib/api';
import type { CronJob } from '@/services/cron.types';

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}));

vi.mock('@/services/cron', () => ({
  updateCronJob: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from 'sonner';
import { updateCronJob } from '@/services/cron';
import { AllowedRootsEditor } from '../AllowedRootsEditor';

const job = { id: 'job-1', allowed_roots: [] } as unknown as CronJob;

function addRootAndSave(path: string): void {
  fireEvent.change(screen.getByPlaceholderText('cron.pathPlaceholder'), { target: { value: path } });
  fireEvent.click(screen.getByText('cron.addPath'));
  fireEvent.click(screen.getByText('cron.save'));
}

describe('AllowedRootsEditor save refusal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('tells the user a too-broad folder is why the folders were not saved', async () => {
    vi.mocked(updateCronJob).mockRejectedValue(
      new ApiError('refused', 40001, [{ field: 'allowed_roots', issue: 'too_broad' }]),
    );
    const onUpdated = vi.fn();
    render(<AllowedRootsEditor job={job} onUpdated={onUpdated} />);

    addRootAndSave('/Users/me');

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('common.workspacePathIssue.tooBroad'));
    expect(onUpdated).not.toHaveBeenCalled();
  });

  it('keeps the generic message for a failure that is not about the folders', async () => {
    vi.mocked(updateCronJob).mockRejectedValue(new ApiError('boom'));
    render(<AllowedRootsEditor job={job} onUpdated={vi.fn()} />);

    addRootAndSave('/data/reports');

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('cron.actionFail'));
  });
});
