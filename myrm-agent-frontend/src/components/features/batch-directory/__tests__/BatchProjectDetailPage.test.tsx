/** @vitest-environment jsdom */
import { act, cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import BatchProjectDetailPage from '@/app/batch-directories/[projectId]/page';
import type { BatchProjectDetail } from '@/services/batch-directory';
import {
  DETAIL_TASKS,
  click,
  deferred,
  mkDetail,
  resetBatchMocks,
  router,
  serviceMocks,
  settle,
  toast,
} from './batchTestKit';

vi.mock('next-intl', () => import('./batchTestKit').then((m) => ({ useTranslations: () => m.t })));
vi.mock('next/navigation', () => import('./batchTestKit').then((m) => ({ useRouter: () => m.router })));
vi.mock('next/link', () => import('./batchTestKit').then((m) => ({ default: m.Link })));
vi.mock('@/hooks/shared/useToast', () => import('./batchTestKit').then((m) => ({ toast: m.toast })));
vi.mock('@/services/batch-directory', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/batch-directory')>()),
  ...(await import('./batchTestKit')).serviceMocks,
}));

const running = (over: Partial<BatchProjectDetail> = {}) =>
  mkDetail({ status: 'running', tasks: DETAIL_TASKS, total_tasks: 13, completed_tasks: 4, failed_tasks: 2, ...over });

async function renderDetail(detail: BatchProjectDetail = running()) {
  serviceMocks.getBatchProject.mockResolvedValue(detail);
  const view = render(<BatchProjectDetailPage params={Promise.resolve({ projectId: 'p1' })} />);
  await settle();
  return view;
}

const taskRow = (title: string) => within(screen.getByText(title).closest('tr') as HTMLElement);
const card = (testId: string) => within(screen.getByTestId(testId));

beforeEach(resetBatchMocks);
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('BatchProjectDetailPage header and summary', () => {
  it('shows a skeleton until the project loads, then the header', async () => {
    const detail = deferred<BatchProjectDetail>();
    serviceMocks.getBatchProject.mockReturnValue(detail.promise);
    render(<BatchProjectDetailPage params={Promise.resolve({ projectId: 'p1' })} />);
    await settle();
    expect(screen.queryByTestId('bd-project-header')).toBeNull();

    detail.resolve(running());
    await settle();
    expect(serviceMocks.getBatchProject).toHaveBeenCalledWith('p1');
    expect(screen.getByTestId('bd-project-name')).toHaveTextContent('Alpha');
    expect(screen.getByTestId('bd-project-status')).toHaveTextContent('statusRunning');
    expect(screen.getByTestId('bd-project-id')).toHaveTextContent('projectIdLabel{"id":"p1"}');
  });

  it('keeps the status badge out of a paragraph so the markup stays valid', async () => {
    await renderDetail();
    expect(screen.getByTestId('bd-project-status').closest('p')).toBeNull();
  });

  it('goes back to the list from the header', async () => {
    await renderDetail();
    await click(screen.getByRole('button', { name: 'backToList' }));
    expect(router.push).toHaveBeenCalledWith('/batch-directories');
  });

  it('summarizes progress and task counts, tinting failures with the readable destructive text token', async () => {
    await renderDetail(mkDetail({ status: 'running', total_tasks: 4, completed_tasks: 1, failed_tasks: 1 }));
    expect(screen.getByText('2/4 (50%)')).toBeInTheDocument();
    expect(document.querySelector<HTMLElement>('[style*="translateX"]')?.style.transform).toBe('translateX(-50%)');

    const tile = (label: string) => screen.getAllByText(label).at(-1)?.previousElementSibling;
    expect(tile('statTotalTasks')).toHaveTextContent('4');
    expect(tile('statCompleted')).toHaveClass('text-emerald-500');
    expect(tile('statFailed')).toHaveTextContent('1');
    expect(tile('statFailed')).toHaveClass('text-destructive-text');
    expect(tile('statFailed')).not.toHaveClass('text-destructive');
  });

  it('shows the configuration with links, fallbacks and the run duration', async () => {
    await renderDetail(mkDetail({ status: 'completed', concurrency: 5, notify_enabled: false }));
    expect(screen.getByRole('link', { name: 'board-9' })).toHaveAttribute('href', '/work');
    expect(screen.getByText('agent-1')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('configDisabled')).toBeInTheDocument();
    expect(screen.getByText(new Date('2026-01-02T03:04:05Z').toLocaleString())).toBeInTheDocument();
    expect(screen.getByTestId('bd-config-duration-value')).toHaveTextContent('1h 1m');
  });

  it('falls back to dashes when board, agent, or timestamps are missing', async () => {
    await renderDetail(
      mkDetail({ status: 'running', board_id: null, agent_id: null, created_at: null, finished_at: null }),
    );
    expect(screen.queryByRole('link', { name: /board/ })).toBeNull();
    expect(screen.getByText('configEnabled')).toBeInTheDocument();
    expect(card('bd-config-duration').getByText('—')).toBeInTheDocument();
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(4);
  });

  it('shows the paused hint with the number of blocked tasks, and the auto refresh hint only while active', async () => {
    const { unmount } = await renderDetail(running({ status: 'paused' }));
    expect(screen.getByText('pausedHint{"count":1}')).toBeInTheDocument();
    expect(screen.getByText('autoRefreshHint')).toBeInTheDocument();
    unmount();

    await renderDetail(running({ status: 'completed' }));
    expect(screen.queryByText(/pausedHint/)).toBeNull();
    expect(screen.queryByText('autoRefreshHint')).toBeNull();
  });
});

describe('BatchProjectDetailPage scope cards', () => {
  it('renders prompt, artifact patterns, directories and missing-artifact directories', async () => {
    await renderDetail(running({ artifact_patterns: ['*.md', 'out/*.csv'] }));
    expect(screen.getByText('Run it')).toBeInTheDocument();
    expect(screen.getByText('*.md')).toBeInTheDocument();
    expect(screen.getByText('out/*.csv')).toBeInTheDocument();

    const dirs = card('bd-directories-card');
    expect(dirs.getByText('dirsCountTitle{"count":3}')).toBeInTheDocument();
    expect(dirs.getByText('/a').parentElement).toHaveClass('bg-muted/40');
    const failedChip = dirs.getByText('/b').parentElement;
    expect(failedChip).toHaveClass('text-destructive-text', 'bg-destructive/10', 'border-destructive/30');
    expect(failedChip).not.toHaveClass('text-destructive');

    const missingTitle = screen.getByText('missingArtifactsTitle');
    expect(missingTitle).toHaveClass('text-destructive-text');
    expect(missingTitle.closest('[class~="border-destructive/40"]')).toHaveClass('bg-destructive/5');
    expect(screen.getAllByText('/c')).toHaveLength(2);
  });

  it('omits empty prompt, patterns, and missing-artifact cards', async () => {
    await renderDetail(
      running({
        prompt: '',
        artifact_patterns: [],
        failed_directories: undefined,
        missing_artifact_directories: undefined,
      }),
    );
    expect(screen.queryByText('promptTitle')).toBeNull();
    expect(screen.queryByText('artifactsTitle')).toBeNull();
    expect(screen.queryByText('missingArtifactsTitle')).toBeNull();
    expect(card('bd-directories-card').getByText('/b').parentElement).toHaveClass('bg-muted/40');
  });
});

describe('BatchProjectDetailPage task table', () => {
  it('maps task status to a label and falls back to pending for unknown statuses', async () => {
    await renderDetail();
    expect(taskRow('Done verified').getByText('taskStatusCompleted')).toBeInTheDocument();
    expect(taskRow('Failed with msg').getByText('taskStatusFailed')).toBeInTheDocument();
    expect(taskRow('Running').getByText('taskStatusRunning')).toBeInTheDocument();
    expect(taskRow('Archived').getByText('taskStatusArchived')).toBeInTheDocument();
    expect(taskRow('In review 1').getByText('taskStatusInReview')).toBeInTheDocument();
    expect(taskRow('Blocked').getByText('taskStatusBlocked')).toBeInTheDocument();
    expect(taskRow('Pending').getByText('taskStatusPending')).toBeInTheDocument();
    expect(taskRow('Weird').getByText('taskStatusPending')).toBeInTheDocument();
    expect(taskRow('Pending').getByText('—', { selector: 'span.truncate' })).toBeInTheDocument();
  });

  it('shows the result column per outcome with the destructive text token for failures', async () => {
    await renderDetail();
    const failed = taskRow('Failed with msg').getByText('boom');
    expect(failed).toHaveAttribute('title', 'boom');
    expect(failed).toHaveClass('text-destructive-text');
    expect(failed).not.toHaveClass('text-destructive');
    expect(taskRow('Failed bare').getByText('taskFailedUnknown')).toBeInTheDocument();

    expect(taskRow('Done verified').getByText('artifactVerified')).toBeInTheDocument();
    expect(taskRow('Done verified').getByText('All good')).toBeInTheDocument();
    const missing = taskRow('Done missing').getByText('artifactMissing');
    expect(missing).toHaveClass('text-destructive-text');
    expect(taskRow('Done bare').getByText('taskCompletedNoResult')).toBeInTheDocument();
    expect(taskRow('Done with result').getByText('Some result text')).toBeInTheDocument();
    expect(taskRow('Done with result').queryByText('taskCompletedNoResult')).toBeNull();
    expect(taskRow('Running').getByText('taskPending')).toBeInTheDocument();
  });

  it('offers a per-task retry only for failed, archived, or artifact-missing tasks', async () => {
    await renderDetail();
    const withRetry = ['Done missing', 'Failed with msg', 'Failed bare', 'Archived'];
    for (const title of DETAIL_TASKS.map((task) => task.title)) {
      expect(taskRow(title).queryByRole('button', { name: /retryTaskAction/ }) !== null, title).toBe(
        withRetry.includes(title),
      );
    }
  });

  it('shows the empty tasks hint', async () => {
    await renderDetail(mkDetail({ status: 'completed', tasks: [] }));
    expect(screen.getByText('emptyTasks')).toBeInTheDocument();
  });
});

describe('BatchProjectDetailPage loading and polling', () => {
  it('shows the not-found view when loading fails and navigates back', async () => {
    serviceMocks.getBatchProject.mockRejectedValue(new Error('gone'));
    render(<BatchProjectDetailPage params={Promise.resolve({ projectId: 'p1' })} />);
    await settle();
    expect(toast.error).toHaveBeenCalledWith('detailLoadError');
    expect(screen.getByText('notFound')).toBeInTheDocument();

    await click(screen.getByRole('button', { name: /backToList/ }));
    expect(router.push).toHaveBeenCalledWith('/batch-directories');
  });

  it('polls every 10 seconds while not terminal and stops once the project finishes', async () => {
    vi.useFakeTimers();
    serviceMocks.getBatchProject.mockResolvedValue(running());
    const advance = (ms: number) => act(async () => void (await vi.advanceTimersByTimeAsync(ms)));
    render(<BatchProjectDetailPage params={Promise.resolve({ projectId: 'p1' })} />);
    await advance(0);
    expect(serviceMocks.getBatchProject).toHaveBeenCalledTimes(1);

    await advance(9_999);
    expect(serviceMocks.getBatchProject).toHaveBeenCalledTimes(1);
    await advance(1);
    expect(serviceMocks.getBatchProject).toHaveBeenCalledTimes(2);

    serviceMocks.getBatchProject.mockResolvedValue(running({ status: 'completed' }));
    await advance(10_000);
    expect(serviceMocks.getBatchProject).toHaveBeenCalledTimes(3);
    expect(screen.queryByText('autoRefreshHint')).toBeNull();

    await advance(60_000);
    expect(serviceMocks.getBatchProject).toHaveBeenCalledTimes(3);
  });

  it('stops polling when the page unmounts', async () => {
    vi.useFakeTimers();
    serviceMocks.getBatchProject.mockResolvedValue(running());
    const advance = (ms: number) => act(async () => void (await vi.advanceTimersByTimeAsync(ms)));
    const { unmount } = render(<BatchProjectDetailPage params={Promise.resolve({ projectId: 'p1' })} />);
    await advance(0);
    unmount();
    await advance(30_000);
    expect(serviceMocks.getBatchProject).toHaveBeenCalledTimes(1);
  });
});
