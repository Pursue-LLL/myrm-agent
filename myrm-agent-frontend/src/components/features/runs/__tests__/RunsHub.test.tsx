/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockListUnifiedRuns = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock('@/services/runs', () => ({
  listUnifiedRuns: (...args: unknown[]) => mockListUnifiedRuns(...args),
}));

import { toast } from 'sonner';
import { RunsHub } from '../RunsHub';

const emptyListResponse = {
  items: [],
  total: 0,
  offset: 0,
  limit: 30,
  has_more: false,
  degraded: false,
  failed_sources: [],
};

const sampleRun = {
  id: 'cron:job-1:run-1',
  source: 'cron' as const,
  status: 'ok' as const,
  title: 'Daily AI digest',
  started_at: new Date().toISOString(),
  finished_at: new Date().toISOString(),
  duration_ms: 1200,
  error: null,
  summary: 'Done',
  output: null,
  metadata: null,
  agent_id: 'agent-1',
  job_id: 'job-1',
  task_id: null,
  has_execution_steps: true,
};

describe('RunsHub', () => {
  beforeEach(() => {
    mockListUnifiedRuns.mockReset();
    vi.mocked(toast.error).mockReset();
    mockListUnifiedRuns.mockResolvedValue(emptyListResponse);
  });

  it('shows error state instead of empty when API fails', async () => {
    mockListUnifiedRuns.mockRejectedValue(new Error('network'));

    render(<RunsHub />);

    await waitFor(() => {
      expect(screen.getByText('loadError')).toBeInTheDocument();
    });

    expect(screen.queryByText('empty')).not.toBeInTheDocument();
    expect(screen.getByText('retry')).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('retries loading after API failure', async () => {
    mockListUnifiedRuns.mockRejectedValueOnce(new Error('network'));
    mockListUnifiedRuns.mockResolvedValueOnce({
      ...emptyListResponse,
      items: [sampleRun],
      total: 1,
    });

    render(<RunsHub />);

    await waitFor(() => {
      expect(screen.getByText('retry')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText('retry'));

    await waitFor(() => {
      expect(screen.getByText('Daily AI digest')).toBeInTheDocument();
    });

    expect(mockListUnifiedRuns).toHaveBeenCalledTimes(2);
  });

  it('renders i18n source and execution step badges', async () => {
    mockListUnifiedRuns.mockResolvedValue({
      ...emptyListResponse,
      items: [sampleRun],
      total: 1,
    });

    render(<RunsHub />);

    await waitFor(() => {
      expect(screen.getByText('sourceCron')).toBeInTheDocument();
    });

    expect(screen.getByText('executionStepsBadge')).toBeInTheDocument();
    expect(screen.queryByText('Cron')).not.toBeInTheDocument();
    expect(screen.queryByText('Transcript')).not.toBeInTheDocument();
  });

  it('shows emptyFiltered when filters are active and list is empty', async () => {
    mockListUnifiedRuns.mockResolvedValue(emptyListResponse);

    render(<RunsHub />);

    await waitFor(() => {
      expect(screen.getByText('empty')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText('filterError'));

    await waitFor(() => {
      expect(screen.getByText('emptyFiltered')).toBeInTheDocument();
    });

    expect(screen.queryByText('empty')).not.toBeInTheDocument();
  });

  it('shows degraded banner when response is partial', async () => {
    mockListUnifiedRuns.mockResolvedValue({
      ...emptyListResponse,
      degraded: true,
      failed_sources: ['cron'],
    });

    render(<RunsHub />);

    await waitFor(() => {
      expect(screen.getByText('degradedBanner')).toBeInTheDocument();
    });
  });

  it('toasts on loadMore failure without clearing the list', async () => {
    const firstPage = {
      ...emptyListResponse,
      items: [sampleRun],
      total: 2,
      has_more: true,
    };
    mockListUnifiedRuns.mockResolvedValueOnce(firstPage);
    mockListUnifiedRuns.mockRejectedValueOnce(new Error('network'));

    render(<RunsHub />);

    await waitFor(() => {
      expect(screen.getByText('Daily AI digest')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText('loadMore'));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('loadError');
    });

    expect(screen.getByText('Daily AI digest')).toBeInTheDocument();
    expect(screen.queryByText('retry')).not.toBeInTheDocument();
  });
});
