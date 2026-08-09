/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockListUnifiedRuns = vi.fn();

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
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

vi.mock(
  '@/components/features/settings/sections/system/ExecutionTraceTimeline',
  () => ({
    default: ({
      sessionId,
      showEvalCase,
      pollMs,
    }: {
      sessionId: string;
      showEvalCase?: boolean;
      pollMs?: number;
    }) => (
      <div
        data-testid="mock-trace-timeline"
        data-session-id={sessionId}
        data-show-eval-case={String(showEvalCase)}
        data-poll-ms={pollMs ?? ''}
      />
    ),
  }),
);

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

  it('expands a kanban run with a task_id to show the execution trace', async () => {
    const kanbanRun = {
      ...sampleRun,
      id: 'kanban:task-1',
      source: 'kanban' as const,
      title: 'Summarize repo',
      job_id: null,
      task_id: 'task-1',
      has_execution_steps: false,
    };
    mockListUnifiedRuns.mockResolvedValue({
      ...emptyListResponse,
      items: [kanbanRun],
      total: 1,
    });

    render(<RunsHub />);

    await waitFor(() => {
      expect(screen.getByText('Summarize repo')).toBeInTheDocument();
    });
    expect(screen.getAllByText('sourceKanban').length).toBeGreaterThan(0);

    await userEvent.click(screen.getByText('Summarize repo'));

    expect(screen.getByText('executionTrace')).toBeInTheDocument();
    const timeline = screen.getByTestId('mock-trace-timeline');
    expect(timeline).toBeInTheDocument();
    expect(timeline).toHaveAttribute('data-session-id', 'task-1');
    expect(timeline).toHaveAttribute('data-show-eval-case', 'false');
    expect(timeline).toHaveAttribute('data-poll-ms', '');
  });

  it('polls the execution trace while a kanban run is running', async () => {
    const runningRun = {
      ...sampleRun,
      id: 'kanban:task-2',
      source: 'kanban' as const,
      title: 'Deploy release',
      job_id: null,
      task_id: 'task-2',
      status: 'running' as const,
      has_execution_steps: false,
    };
    mockListUnifiedRuns.mockResolvedValue({
      ...emptyListResponse,
      items: [runningRun],
      total: 1,
    });

    render(<RunsHub />);

    await waitFor(() => {
      expect(screen.getByText('Deploy release')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText('Deploy release'));

    const timeline = screen.getByTestId('mock-trace-timeline');
    expect(timeline).toHaveAttribute('data-session-id', 'task-2');
    expect(timeline).toHaveAttribute('data-poll-ms', '30000');
  });

  it('silently refreshes the list while a run is running, keeping current offset', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const runningRun = {
        ...sampleRun,
        id: 'kanban:task-3',
        source: 'kanban' as const,
        title: 'Nightly sync',
        job_id: null,
        task_id: 'task-3',
        status: 'running' as const,
        has_execution_steps: false,
      };
      mockListUnifiedRuns.mockResolvedValue({
        ...emptyListResponse,
        items: [runningRun],
        total: 1,
      });

      render(<RunsHub />);

      await waitFor(() => {
        expect(screen.getByText('Nightly sync')).toBeInTheDocument();
      });

      const firstCall = mockListUnifiedRuns.mock.calls.length;
      await vi.advanceTimersByTimeAsync(30_000);

      await waitFor(() => {
        expect(mockListUnifiedRuns.mock.calls.length).toBeGreaterThan(firstCall);
      });
      // Poll keeps the previous list position (offset from loaded items) instead of resetting to 0.
      const pollCall = mockListUnifiedRuns.mock.calls.at(-1)?.[0];
      expect(pollCall).toEqual({ status: undefined, source: undefined, limit: 30, offset: 1 });
      // Silent poll must not set the full-list loading state.
      expect(screen.queryByText('retry')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('ignores silent poll failures without clearing the list', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const runningRun = {
        ...sampleRun,
        id: 'kanban:task-4',
        source: 'kanban' as const,
        title: 'Cache warm',
        job_id: null,
        task_id: 'task-4',
        status: 'running' as const,
        has_execution_steps: false,
      };
      mockListUnifiedRuns
        .mockResolvedValueOnce({
          ...emptyListResponse,
          items: [runningRun],
          total: 1,
        })
        .mockRejectedValueOnce(new Error('network'));

      render(<RunsHub />);

      await waitFor(() => {
        expect(screen.getByText('Cache warm')).toBeInTheDocument();
      });

      await vi.advanceTimersByTimeAsync(30_000);
      await vi.advanceTimersByTimeAsync(0);

      // The failed silent poll must not blow away the current list into the error state.
      expect(screen.getByText('Cache warm')).toBeInTheDocument();
      expect(screen.queryByText('retry')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not render trace section for non-kanban runs without a task_id', async () => {
    mockListUnifiedRuns.mockResolvedValue({
      ...emptyListResponse,
      items: [sampleRun],
      total: 1,
    });

    render(<RunsHub />);

    await waitFor(() => {
      expect(screen.getByText('Daily AI digest')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText('Daily AI digest'));

    expect(screen.queryByText('executionTrace')).not.toBeInTheDocument();
    expect(screen.queryByTestId('mock-trace-timeline')).not.toBeInTheDocument();
  });
});
