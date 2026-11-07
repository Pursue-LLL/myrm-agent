/** @vitest-environment jsdom */
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import BatchDirectoriesPage from '@/app/batch-directories/page';
import type { BatchProject } from '@/services/batch-directory';
import {
  click,
  deferred,
  listBoards,
  mkDetail,
  mkProject,
  resetBatchMocks,
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
vi.mock('@/services/kanban', () => import('./batchTestKit').then((m) => ({ listBoards: m.listBoards })));
vi.mock('@/services/chat', () => import('./batchTestKit').then((m) => ({ browseDirectories: m.browseDirectories })));
vi.mock('@/services/riskHeldToast', () =>
  import('./batchTestKit').then((m) => ({ isRiskHeldError: m.isRiskHeldError })),
);

const PROJECTS: BatchProject[] = [
  mkProject({
    project_id: 'p-run',
    name: 'Running one',
    status: 'running',
    total_tasks: 7,
    completed_tasks: 2,
    failed_tasks: 1,
  }),
  mkProject({
    project_id: 'p-done',
    name: 'Done one',
    status: 'completed',
    total_tasks: 3,
    completed_tasks: 3,
    failed_tasks: 0,
    created_at: null,
  }),
  mkProject({
    project_id: 'p-fail',
    name: 'Failed one',
    status: 'failed',
    total_tasks: 3,
    completed_tasks: 0,
    failed_tasks: 3,
  }),
  mkProject({
    project_id: 'p-draft',
    name: 'Draft one',
    status: 'draft',
    total_tasks: 0,
    completed_tasks: 0,
    failed_tasks: 0,
    directories: [],
  }),
  mkProject({ project_id: 'p-odd', name: 'Odd one', status: 'queued' as BatchProject['status'] }),
];

const rows = () => screen.getAllByTestId('bd-project-row');
const statValue = (label: string) => screen.getByText(label).nextElementSibling?.textContent;
const progressOffset = (row: HTMLElement) => row.querySelector<HTMLElement>('[style*="translateX"]')?.style.transform;

async function renderLoaded(projects: BatchProject[] = PROJECTS) {
  serviceMocks.listBatchProjects.mockResolvedValue(projects);
  listBoards.mockResolvedValue({ items: [] });
  render(<BatchDirectoriesPage />);
  await settle();
}

beforeEach(resetBatchMocks);
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('BatchDirectoriesPage list', () => {
  it('shows a skeleton while loading, then the heading and rows', async () => {
    const list = deferred<BatchProject[]>();
    serviceMocks.listBatchProjects.mockReturnValue(list.promise);
    listBoards.mockResolvedValue({ items: [] });
    render(<BatchDirectoriesPage />);
    expect(screen.queryByText('pageTitle')).toBeNull();

    list.resolve(PROJECTS);
    await settle();
    expect(screen.getByText('pageTitle')).toBeInTheDocument();
    expect(rows()).toHaveLength(PROJECTS.length);
  });

  it('aggregates the stat cards across projects', async () => {
    await renderLoaded();
    expect(statValue('statProjects')).toBe('5');
    expect(statValue('statRunning')).toBe('1');
    expect(statValue('statCompleted')).toBe('6');
    expect(statValue('statFailed')).toBe('5');
  });

  it('renders a row per project with link, progress, directory count and creation time', async () => {
    await renderLoaded();
    const [running, done, , draft] = rows();

    const name = within(running).getByTestId('bd-project-row-name');
    expect(name).toHaveTextContent('Running one');
    expect(name).toHaveAttribute('href', '/batch-directories/p-run');
    expect(within(running).getByText('2/7')).toBeInTheDocument();
    expect(progressOffset(running)).toBe('translateX(-57%)');
    expect(within(running).getByText('dirsCount{"count":2}')).toBeInTheDocument();
    expect(within(running).getByText(new Date('2026-01-02T03:04:05Z').toLocaleString())).toBeInTheDocument();

    expect(progressOffset(done)).toBe('translateX(0%)');
    expect(done).toHaveTextContent('—');
    expect(progressOffset(draft)).toBe('translateX(-100%)');
    expect(within(draft).getByText('dirsCount{"count":0}')).toBeInTheDocument();
  });

  it('maps every status to its badge and falls back to draft for unknown statuses', async () => {
    await renderLoaded();
    const badges = screen.getAllByTestId('bd-project-row-status').map((b) => b.textContent);
    expect(badges).toEqual(['statusRunning', 'statusCompleted', 'statusFailed', 'statusDraft', 'statusDraft']);
  });

  it('styles the failed badge with the readable destructive text token and tints', async () => {
    await renderLoaded();
    const failed = screen.getAllByTestId('bd-project-row-status')[2];
    expect(failed).toHaveClass('text-destructive-text', 'bg-destructive/10', 'border-destructive/30');
    expect(failed).not.toHaveClass('text-destructive');
  });

  it('shows the empty state without rows', async () => {
    await renderLoaded([]);
    expect(screen.getByText('emptyState')).toBeInTheDocument();
    expect(screen.queryByTestId('bd-project-row')).toBeNull();
  });

  it('reports a list load failure and keeps the page usable', async () => {
    serviceMocks.listBatchProjects.mockRejectedValue(new Error('down'));
    listBoards.mockResolvedValue({ items: [] });
    render(<BatchDirectoriesPage />);
    await settle();
    expect(toast.error).toHaveBeenCalledWith('listError');
    expect(screen.getByText('emptyState')).toBeInTheDocument();
  });
});

describe('BatchDirectoriesPage row actions', () => {
  it('offers cancel only for running projects and delete for the rest', async () => {
    await renderLoaded();
    const cancelButtons = screen.getAllByRole('button', { name: 'cancelAction' });
    expect(cancelButtons).toHaveLength(1);
    expect(within(rows()[0]).getByRole('button', { name: 'cancelAction' })).toBe(cancelButtons[0]);
    expect(screen.getAllByRole('button', { name: /^deleteLabel/ })).toHaveLength(PROJECTS.length - 1);
  });

  it('cancels after confirmation, shows progress while pending, then refreshes', async () => {
    await renderLoaded();
    const cancel = deferred<ReturnType<typeof mkDetail>>();
    serviceMocks.cancelBatchProject.mockReturnValue(cancel.promise);

    await click(screen.getByRole('button', { name: 'cancelAction' }));
    expect(screen.getByText('confirmCancelTitle{"name":"Running one"}')).toBeInTheDocument();
    await click(screen.getByRole('button', { name: 'confirmCancelAction' }));

    expect(serviceMocks.cancelBatchProject).toHaveBeenCalledWith('p-run');
    expect(within(rows()[0]).getByRole('button', { name: '' })).toBeDisabled();

    cancel.resolve(mkDetail());
    await settle();
    expect(toast.success).toHaveBeenCalledWith('cancelSuccess{"name":"Running one"}');
    expect(serviceMocks.listBatchProjects).toHaveBeenCalledTimes(2);
    expect(within(rows()[0]).getByRole('button', { name: 'cancelAction' })).toBeEnabled();
  });

  it('does not cancel when the confirmation is dismissed', async () => {
    await renderLoaded();
    await click(screen.getByRole('button', { name: 'cancelAction' }));
    await click(screen.getByRole('button', { name: 'cancelButton' }));
    expect(serviceMocks.cancelBatchProject).not.toHaveBeenCalled();
    expect(screen.queryByText('confirmCancelDescription')).toBeNull();
  });

  it('reports a cancel failure without refreshing', async () => {
    await renderLoaded();
    serviceMocks.cancelBatchProject.mockRejectedValue(new Error('no'));
    await click(screen.getByRole('button', { name: 'cancelAction' }));
    await click(screen.getByRole('button', { name: 'confirmCancelAction' }));
    expect(toast.error).toHaveBeenCalledWith('cancelError');
    expect(serviceMocks.listBatchProjects).toHaveBeenCalledTimes(1);
    expect(within(rows()[0]).getByRole('button', { name: 'cancelAction' })).toBeEnabled();
  });

  it('deletes after confirmation with a destructive confirm button, then refreshes', async () => {
    await renderLoaded();
    serviceMocks.deleteBatchProject.mockResolvedValue(undefined);
    const trigger = screen.getByRole('button', { name: 'deleteLabel{"name":"Done one"}' });
    expect(trigger).toHaveClass('text-destructive-text');
    expect(trigger).not.toHaveClass('text-destructive');

    await click(trigger);
    expect(screen.getByText('confirmDeleteTitle{"name":"Done one"}')).toBeInTheDocument();
    const confirm = screen.getByRole('button', { name: 'confirmDeleteAction' });
    expect(confirm).toHaveClass('bg-destructive', 'text-destructive-foreground');
    await click(confirm);

    expect(serviceMocks.deleteBatchProject).toHaveBeenCalledWith('p-done');
    expect(toast.success).toHaveBeenCalledWith('deleteSuccess{"name":"Done one"}');
    expect(serviceMocks.listBatchProjects).toHaveBeenCalledTimes(2);
  });

  it('keeps the project when delete is dismissed or fails', async () => {
    await renderLoaded();
    const trigger = () => screen.getByRole('button', { name: 'deleteLabel{"name":"Done one"}' });
    await click(trigger());
    await click(screen.getByRole('button', { name: 'cancelButton' }));
    expect(serviceMocks.deleteBatchProject).not.toHaveBeenCalled();

    serviceMocks.deleteBatchProject.mockRejectedValue(new Error('no'));
    await click(trigger());
    await click(screen.getByRole('button', { name: 'confirmDeleteAction' }));
    expect(toast.error).toHaveBeenCalledWith('deleteError');
    expect(serviceMocks.listBatchProjects).toHaveBeenCalledTimes(1);
  });
});
