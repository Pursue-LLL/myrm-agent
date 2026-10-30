// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
import { CronTimeoutEditor } from '../CronTimeoutEditor';

const job = { id: 'job-1', timeout_seconds: 300 } as unknown as CronJob;

const input = (): HTMLInputElement => screen.getByRole('spinbutton', { name: 'cron.timeoutLabel' }) as HTMLInputElement;
const saveButton = (): HTMLButtonElement => screen.getByRole('button', { name: 'cron.save' }) as HTMLButtonElement;

describe('CronTimeoutEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the job limit and has nothing to save until it changes', () => {
    render(<CronTimeoutEditor job={job} onUpdated={vi.fn()} />);

    expect(input().value).toBe('300');
    expect(saveButton().disabled).toBe(true);
  });

  it('saves a new limit as whole seconds and reports it', async () => {
    vi.mocked(updateCronJob).mockResolvedValue(job);
    const onUpdated = vi.fn();
    render(<CronTimeoutEditor job={job} onUpdated={onUpdated} />);

    fireEvent.change(input(), { target: { value: '900' } });
    fireEvent.click(saveButton());

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('cron.timeoutUpdated'));
    expect(updateCronJob).toHaveBeenCalledWith('job-1', { timeout_seconds: 900 });
    expect(onUpdated).toHaveBeenCalledTimes(1);
  });

  it.each(['', '9', '3601', '2.5', 'abc'])('does not offer to save the limit "%s"', (typed) => {
    render(<CronTimeoutEditor job={job} onUpdated={vi.fn()} />);

    fireEvent.change(input(), { target: { value: typed } });

    expect(saveButton().disabled).toBe(true);
    expect(input().getAttribute('aria-invalid')).toBe('true');
  });

  it('keeps the form and reports a refused save', async () => {
    vi.mocked(updateCronJob).mockRejectedValue(new Error('boom'));
    const onUpdated = vi.fn();
    render(<CronTimeoutEditor job={job} onUpdated={onUpdated} />);

    fireEvent.change(input(), { target: { value: '600' } });
    fireEvent.click(saveButton());

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('cron.actionFail'));
    expect(onUpdated).not.toHaveBeenCalled();
    expect(input().value).toBe('600');
  });

  it('follows the job when the limit is changed elsewhere', () => {
    const { rerender } = render(<CronTimeoutEditor job={job} onUpdated={vi.fn()} />);

    rerender(<CronTimeoutEditor job={{ ...job, timeout_seconds: 1200 } as CronJob} onUpdated={vi.fn()} />);

    expect(input().value).toBe('1200');
  });
});
