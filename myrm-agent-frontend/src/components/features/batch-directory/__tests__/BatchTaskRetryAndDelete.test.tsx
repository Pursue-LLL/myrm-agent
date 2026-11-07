/** @vitest-environment jsdom */
import { cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import BatchProjectDetailPage from '@/app/batch-directories/[projectId]/page';
import type { BatchProjectDetail, BatchProjectStatus } from '@/services/batch-directory';
import {
  click,
  deferred,
  detailOf,
  dialog,
  confirmWith,
  resetBatchMocks,
  retryTaskButtons,
  router,
  serviceMocks,
  settle,
  startAction,
  taskRetryButton,
  toast,
  trigger,
} from './batchTestKit';

vi.mock('next-intl', () => import('./batchTestKit').then((m) => ({ useTranslations: () => m.t })));
vi.mock('next/navigation', () => import('./batchTestKit').then((m) => ({ useRouter: () => m.router })));
vi.mock('next/link', () => import('./batchTestKit').then((m) => ({ default: m.Link })));
vi.mock('@/hooks/shared/useToast', () => import('./batchTestKit').then((m) => ({ toast: m.toast })));
vi.mock('@/services/batch-directory', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/batch-directory')>()),
  ...(await import('./batchTestKit')).serviceMocks,
}));

async function renderDetail(status: BatchProjectStatus) {
  serviceMocks.getBatchProject.mockResolvedValue(detailOf(status));
  const view = render(<BatchProjectDetailPage params={Promise.resolve({ projectId: 'p1' })} />);
  await settle();
  return view;
}

beforeEach(resetBatchMocks);
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('BatchTaskTable per-task retry', () => {
  it('retries one task after confirmation and only locks that row meanwhile', async () => {
    const pending = deferred<BatchProjectDetail>();
    serviceMocks.retryBatchTask.mockReturnValue(pending.promise);
    await renderDetail('completed');
    expect(retryTaskButtons()).toHaveLength(4);

    await click(taskRetryButton('Failed with msg'));
    expect(dialog().getByText('confirmRetryTaskTitle')).toBeInTheDocument();
    await confirmWith('confirmRetryTaskAction');
    expect(serviceMocks.retryBatchTask).toHaveBeenCalledExactlyOnceWith('p1', 't-fail');
    expect(taskRetryButton('Failed with msg')).toBeDisabled();
    expect(taskRetryButton('Failed bare')).toBeEnabled();
    expect(taskRetryButton('Archived')).toBeEnabled();

    pending.resolve(detailOf('completed', { retried_task_ids: ['t-fail'] }));
    await settle();
    expect(toast.success).toHaveBeenCalledExactlyOnceWith('retryTaskSuccess{"count":1}');
    expect(serviceMocks.getBatchProject).toHaveBeenCalledTimes(2);
    expect(taskRetryButton('Failed with msg')).toBeEnabled();
  });

  it('reports a failed task retry without refreshing', async () => {
    serviceMocks.retryBatchTask.mockRejectedValue(new Error('nope'));
    await renderDetail('completed');
    await click(taskRetryButton('Archived'));
    await confirmWith('confirmRetryTaskAction');
    expect(toast.error).toHaveBeenCalledExactlyOnceWith('retryTaskError');
    expect(serviceMocks.getBatchProject).toHaveBeenCalledTimes(1);
    expect(taskRetryButton('Archived')).toBeEnabled();
  });

  it.each(['retry', 'rerun'] as const)('disables every task retry while the project %s is pending', async (key) => {
    const service = key === 'retry' ? 'retryBatchProject' : 'rerunBatchProject';
    serviceMocks[service].mockReturnValue(deferred<BatchProjectDetail>().promise);
    await renderDetail('completed');
    await startAction({ key, confirm: key === 'rerun' ? 'confirmRerunAction' : undefined });
    for (const button of retryTaskButtons()) {
      expect(button).toBeDisabled();
    }
  });
});

describe('BatchProjectToolbar delete', () => {
  it('uses the readable destructive text token on the trigger and a solid destructive confirm button', async () => {
    await renderDetail('completed');
    expect(trigger('delete')).toHaveClass('text-destructive-text');
    expect(trigger('delete')).not.toHaveClass('text-destructive');

    await click(trigger('delete'));
    expect(dialog().getByText('confirmDeleteTitle{"name":"Alpha"}')).toBeInTheDocument();
    expect(dialog().getByRole('button', { name: 'confirmDeleteAction' })).toHaveClass(
      'bg-destructive',
      'text-destructive-foreground',
    );
  });

  it('deletes after confirmation, reports success, and returns to the list without refetching', async () => {
    serviceMocks.deleteBatchProject.mockResolvedValue(undefined);
    await renderDetail('completed');
    await startAction({ key: 'delete', confirm: 'confirmDeleteAction' });

    expect(serviceMocks.deleteBatchProject).toHaveBeenCalledExactlyOnceWith('p1');
    expect(toast.success).toHaveBeenCalledExactlyOnceWith('deleteSuccess{"name":"Alpha"}');
    expect(router.push).toHaveBeenCalledExactlyOnceWith('/batch-directories');
    expect(serviceMocks.getBatchProject).toHaveBeenCalledTimes(1);
  });

  it('stays on the page and reports an error when deleting fails', async () => {
    serviceMocks.deleteBatchProject.mockRejectedValue(new Error('nope'));
    await renderDetail('completed');
    await startAction({ key: 'delete', confirm: 'confirmDeleteAction' });

    expect(toast.error).toHaveBeenCalledExactlyOnceWith('deleteError');
    expect(router.push).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('does not delete when the confirmation is dismissed', async () => {
    await renderDetail('completed');
    await click(trigger('delete'));
    await click(dialog().getByRole('button', { name: 'cancelButton' }));
    expect(serviceMocks.deleteBatchProject).not.toHaveBeenCalled();
    expect(router.push).not.toHaveBeenCalled();
  });
});
